from django.contrib.auth import authenticate
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.crypto import get_random_string
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from .api_permissions import IsCashier, IsDirector, IsDirectorOrCashier, IsWaiter
from .api_serializers import (
    CreateOrderSerializer,
    MenuCategorySerializer,
    MenuItemSerializer,
    MenuItemWriteSerializer,
    PaymentCreateSerializer,
    PaymentListSerializer,
    PaymentUpdateSerializer,
    RejectCancelSerializer,
    TableListSerializer,
    TableWriteSerializer,
    UserProfileSerializer,
    build_dashboard_summary,
    get_user_profile,
    serialize_order,
    waiter_user_payload,
)
from .models import DiningTable, MenuCategory, Order, OrderItem, Payment, Product, ProductDailyStock, UserProfile, Waiter
from .services import ACTIVE_ORDER_STATUSES, order_payable_total

User = get_user_model()

def ensure_waiter_instance(user):
    waiter = getattr(user, "waiter_profile", None)
    profile = getattr(user, "profile", None)
    if waiter is None:
        waiter = Waiter.objects.create(
            user=user,
            full_name=profile.full_name if profile else user.username,
            phone=profile.phone if profile else "",
            shift=profile.shift if profile else "",
            experience=profile.experience if profile else "",
        )
    else:
        if profile:
            waiter.full_name = profile.full_name
            waiter.phone = profile.phone
            waiter.shift = profile.shift
            waiter.experience = profile.experience
            waiter.save(update_fields=["full_name", "phone", "shift", "experience"])
    return waiter


def ensure_profile(user):
    profile = getattr(user, "profile", None)
    if profile is None:
        default_role = UserProfile.Role.CASHIER if user.username.lower().startswith("kass") else UserProfile.Role.WAITER
        profile = UserProfile.objects.create(
            user=user,
            full_name=user.get_full_name() or user.username,
            role=default_role,
            phone="",
            shift="",
            experience="",
        )
    return profile


def table_has_open_bill(table: DiningTable) -> bool:
    return Order.objects.filter(table=table, status__in=ACTIVE_ORDER_STATUSES).exists()


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        username = request.data.get("username", "").strip()
        password = request.data.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response({"detail": "Login yoki parol noto'g'ri."}, status=status.HTTP_401_UNAUTHORIZED)

        refresh = RefreshToken.for_user(user)
        profile = ensure_profile(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "full_name": profile.full_name if profile else user.username,
                    "role": profile.role if profile else "",
                },
            }
        )


class MeView(APIView):
    def get(self, request):
        profile = ensure_profile(request.user)
        return Response(UserProfileSerializer(profile).data)


class TablesListView(APIView):
    def get(self, request):
        include_waiters = request.query_params.get("include_waiters") == "true"
        status_filter = request.query_params.get("status")
        tables = DiningTable.objects.prefetch_related("assigned_waiters__profile")
        results = []
        for table in tables:
            table_status = table.current_status
            if status_filter and table_status != status_filter:
                continue
            results.append(TableListSerializer(table, context={"include_waiters": include_waiters}).data)
        return Response(results)


class StaffTablesView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [permissions.IsAuthenticated()]
        return [IsDirector()]

    def get(self, request):
        include_waiters = request.query_params.get("include_waiters") == "true"
        status_filter = request.query_params.get("status")
        tables = DiningTable.objects.prefetch_related("assigned_waiters__profile")
        results = []
        for table in tables:
            table_status = table.current_status
            if status_filter and table_status != status_filter:
                continue
            results.append(TableListSerializer(table, context={"include_waiters": include_waiters}).data)
        return Response(results)

    def post(self, request):
        serializer = TableWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        table = serializer.save()
        return Response(TableListSerializer(table, context={"include_waiters": True}).data, status=status.HTTP_201_CREATED)


class TableJoinView(APIView):
    permission_classes = [IsWaiter]

    def post(self, request, table_id):
        table = get_object_or_404(DiningTable.objects.prefetch_related("assigned_waiters__profile"), pk=table_id)
        table.assigned_waiters.add(request.user)
        return Response(TableListSerializer(table, context={"include_waiters": True}).data)


class MenuCategoryListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [permissions.IsAuthenticated()]
        return [IsDirector()]

    def get(self, request):
        return Response(MenuCategorySerializer(MenuCategory.objects.all(), many=True).data)

    def post(self, request):
        serializer = MenuCategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        category = MenuCategory.objects.create(**serializer.validated_data)
        return Response(MenuCategorySerializer(category).data, status=status.HTTP_201_CREATED)


class MenuCategoryDetailView(APIView):
    permission_classes = [IsDirector]

    def patch(self, request, pk):
        category = get_object_or_404(MenuCategory, pk=pk)
        serializer = MenuCategorySerializer(category, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for key, value in serializer.validated_data.items():
            setattr(category, key, value)
        category.save()
        return Response(MenuCategorySerializer(category).data)

    def delete(self, request, pk):
        category = get_object_or_404(MenuCategory, pk=pk)
        category.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MenuItemsListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [permissions.IsAuthenticated()]
        return [IsDirector()]

    def get(self, request):
        items = Product.objects.select_related("category").all()
        category_id = request.query_params.get("category_id")
        is_active = request.query_params.get("is_active")
        if category_id:
            items = items.filter(category_id=category_id)
        if is_active is not None:
            items = items.filter(is_active=is_active.lower() == "true")
        return Response(MenuItemSerializer(items, many=True).data)

    def post(self, request):
        serializer = MenuItemWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save()
        return Response(MenuItemSerializer(item).data, status=status.HTTP_201_CREATED)


class MenuItemDetailView(APIView):
    permission_classes = [IsDirector]

    def patch(self, request, pk):
        item = get_object_or_404(Product, pk=pk)
        serializer = MenuItemWriteSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        item = serializer.save()
        return Response(MenuItemSerializer(item).data)

    def delete(self, request, pk):
        item = get_object_or_404(Product, pk=pk)
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class OrdersListCreateView(APIView):
    def get(self, request):
        orders = Order.objects.select_related("table", "waiter__user", "waiter__user__profile").prefetch_related("items__product")
        profile = getattr(request.user, "profile", None)
        if profile is None:
            profile = ensure_profile(request.user)
        if profile and profile.role == UserProfile.Role.WAITER:
            orders = orders.filter(waiter__user=request.user)

        status_filter = request.query_params.get("status")
        table_id = request.query_params.get("table_id")
        waiter_id = request.query_params.get("waiter_id")
        date = request.query_params.get("date")
        if status_filter:
            status_map = {
                "active": [Order.Status.NEW, Order.Status.ACCEPTED],
                "rejected": [Order.Status.PARTIALLY_REJECTED],
                "paid": [Order.Status.COMPLETED],
                "cancelled": [Order.Status.CANCELLED],
            }
            orders = orders.filter(status__in=status_map.get(status_filter, []))
        if table_id:
            orders = orders.filter(table_id=table_id)
        if waiter_id:
            orders = orders.filter(waiter__user_id=waiter_id)
        if date:
            orders = orders.filter(created_at__date=date)

        data = [serialize_order(order, include_items=True) for order in orders.order_by("-created_at")]
        return Response(data)

    def post(self, request):
        profile = ensure_profile(request.user)
        if not profile or profile.role != UserProfile.Role.WAITER:
            return Response({"detail": "Faqat waiter order yarata oladi."}, status=status.HTTP_403_FORBIDDEN)

        serializer = CreateOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        table = get_object_or_404(DiningTable, pk=validated["table_id"])
        waiter = ensure_waiter_instance(request.user)
        auto_accept = True  # Ofitsant zakaz urgan zahoti oshxonaga boradi (kassir tasdiqlashi shart emas)
        today = timezone.localdate()

        with transaction.atomic():
            external_id = f"API-{request.user.id}-{get_random_string(16)}"
            order = Order.objects.create(
                external_id=external_id,
                waiter=waiter,
                table=table,
                bill_number=validated.get("bill_number", 1),
                note=validated.get("note", ""),
                status=Order.Status.ACCEPTED if auto_accept else Order.Status.NEW,
                order_source=Order.OrderSource.WAITER,
            )
            for item in validated["items"]:
                product = get_object_or_404(Product, pk=item["menu_item_id"], is_active=True)
                remaining = product.get_today_remaining()
                if remaining is not None and remaining < item["quantity"]:
                    transaction.set_rollback(True)
                    return Response(
                        {"detail": f"{product.name} sig'imi yetarli emas. Qolgan: {remaining}"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=item["quantity"],
                    status=OrderItem.Status.ACCEPTED if auto_accept else OrderItem.Status.PENDING,
                    note=item.get("note", ""),
                )
                stock = ProductDailyStock.objects.filter(product=product, date=today).first()
                if stock:
                    stock.remaining_quantity = max(0, stock.remaining_quantity - item["quantity"])
                    stock.save(update_fields=["remaining_quantity", "updated_at"])
            if auto_accept:
                table.assigned_waiters.add(request.user)

        order = Order.objects.select_related("table", "waiter__user", "waiter__user__profile").prefetch_related("items__product").get(pk=order.pk)
        return Response(serialize_order(order), status=status.HTTP_201_CREATED)


class OrderDetailView(APIView):
    def get(self, request, order_id):
        order = get_object_or_404(
            Order.objects.select_related("table", "waiter__user", "waiter__user__profile").prefetch_related("items__product"),
            pk=order_id,
        )
        profile = ensure_profile(request.user)
        if profile and profile.role == UserProfile.Role.WAITER and order.waiter.user_id != request.user.id:
            return Response({"detail": "Bu order sizga tegishli emas."}, status=status.HTTP_403_FORBIDDEN)
        return Response(serialize_order(order))


class RejectOrderView(APIView):
    permission_classes = [IsDirectorOrCashier]

    def post(self, request, order_id):
        serializer = RejectCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = get_object_or_404(Order, pk=order_id)
        order.status = Order.Status.PARTIALLY_REJECTED
        order.status_reason = serializer.validated_data["reason"]
        order.save(update_fields=["status", "status_reason", "updated_at"])
        return Response({"id": order.id, "status": "rejected", "reason": order.status_reason})


class CancelOrderView(APIView):
    def post(self, request, order_id):
        serializer = RejectCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = get_object_or_404(Order, pk=order_id)
        profile = ensure_profile(request.user)
        if profile and profile.role == UserProfile.Role.WAITER and order.waiter.user_id != request.user.id:
            return Response({"detail": "Bu order sizga tegishli emas."}, status=status.HTTP_403_FORBIDDEN)

        order.status = Order.Status.CANCELLED
        order.status_reason = serializer.validated_data["reason"]
        order.save(update_fields=["status", "status_reason", "updated_at"])
        return Response({"id": order.id, "status": "cancelled", "reason": order.status_reason})


class PaymentsView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [IsCashier()]
        return [IsDirectorOrCashier()]

    def post(self, request):
        serializer = PaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = get_object_or_404(
            Order.objects.select_related("waiter__user", "waiter__user__profile", "table"),
            pk=serializer.validated_data["order_id"],
        )
        if hasattr(order, "payment"):
            return Response({"detail": "Bu order uchun to'lov allaqachon qilingan."}, status=status.HTTP_400_BAD_REQUEST)
        expected_amount = order_payable_total(order)
        if serializer.validated_data["amount"] != expected_amount:
            return Response(
                {
                    "detail": "To'lov summasi buyurtma hisobiga mos emas.",
                    "expected_amount": expected_amount,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment = Payment.objects.create(
            order=order,
            payment_method=serializer.validated_data["payment_method"],
            amount=serializer.validated_data["amount"],
            cashier=request.user,
        )
        order.status = Order.Status.COMPLETED
        order.status_reason = ""
        order.save(update_fields=["status", "status_reason", "updated_at"])
        cashier_profile = ensure_profile(request.user)
        return Response(
            {
                "id": payment.id,
                "order_id": order.id,
                "payment_method": payment.payment_method,
                "amount": payment.amount,
                "paid_at": payment.paid_at,
                "cashier": {
                    "id": request.user.id,
                    "username": request.user.username,
                    "full_name": cashier_profile.full_name if cashier_profile else request.user.username,
                },
            },
            status=status.HTTP_201_CREATED,
        )

    def get(self, request):
        payments = Payment.objects.select_related("order__table", "order__waiter__user", "order__waiter__user__profile", "cashier__profile")
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        payment_method = request.query_params.get("payment_method")
        cashier_id = request.query_params.get("cashier_id")
        if date_from:
            payments = payments.filter(paid_at__date__gte=date_from)
        if date_to:
            payments = payments.filter(paid_at__date__lte=date_to)
        if payment_method:
            payments = payments.filter(payment_method=payment_method)
        if cashier_id:
            payments = payments.filter(cashier_id=cashier_id)
        data = [
            {
                "id": payment.id,
                "order_id": payment.order_id,
                "table_number": payment.order.table.number,
                "waiter_name": waiter_user_payload(payment.order.waiter)["full_name"],
                "payment_method": payment.payment_method,
                "amount": payment.amount,
                "paid_at": payment.paid_at,
            }
            for payment in payments.order_by("-paid_at")
        ]
        return Response(data)


class PaymentDetailView(APIView):
    permission_classes = [IsDirectorOrCashier]

    def get_payment(self, payment_id):
        return generics.get_object_or_404(
            Payment.objects.select_related(
                "order__table",
                "order__waiter__user",
                "order__waiter__user__profile",
                "cashier__profile",
            ),
            pk=payment_id,
        )

    def serialize_payment(self, payment):
        cashier_profile = getattr(payment.cashier, "profile", None)
        return {
            "id": payment.id,
            "order_id": payment.order_id,
            "table_number": payment.order.table.number,
            "waiter_name": waiter_user_payload(payment.order.waiter)["full_name"],
            "payment_method": payment.payment_method,
            "amount": payment.amount,
            "paid_at": payment.paid_at,
            "cashier": {
                "id": payment.cashier_id,
                "username": payment.cashier.username,
                "full_name": cashier_profile.full_name if cashier_profile else payment.cashier.username,
            },
        }

    def get(self, request, payment_id):
        payment = self.get_payment(payment_id)
        return Response(self.serialize_payment(payment))

    def patch(self, request, payment_id):
        payment = self.get_payment(payment_id)
        serializer = PaymentUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(payment, field, value)
        payment.save(update_fields=[*serializer.validated_data.keys()])
        return Response(self.serialize_payment(payment))


class DashboardSummaryView(APIView):
    permission_classes = [IsDirectorOrCashier]

    def get(self, request):
        return Response(build_dashboard_summary())


class WaitersOverviewView(APIView):
    permission_classes = [IsDirectorOrCashier]

    def get(self, request):
        waiters = User.objects.filter(profile__role=UserProfile.Role.WAITER).select_related("profile").prefetch_related("assigned_tables")
        data = []
        for user in waiters:
            waiter = getattr(user, "waiter_profile", None)
            active_orders_count = 0
            rejected_orders_count = 0
            if waiter:
                active_orders_count = waiter.orders.filter(status__in=[Order.Status.NEW, Order.Status.ACCEPTED]).count()
                rejected_orders_count = waiter.orders.filter(status=Order.Status.PARTIALLY_REJECTED).count()
            data.append(
                {
                    "id": user.id,
                    "username": user.username,
                    "full_name": user.profile.full_name,
                    "tables": list(user.assigned_tables.order_by("number").values_list("number", flat=True)),
                    "active_orders_count": active_orders_count,
                    "rejected_orders_count": rejected_orders_count,
                }
            )
        return Response(data)
