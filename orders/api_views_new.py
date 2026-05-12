"""Yangi API view'lar: Direktor, Kassir, Mijoz, Ofitsant kengaytmalari."""
import io
from datetime import timedelta
from decimal import Decimal

import qrcode
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Sum, Count, Q
from django.http import HttpResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.crypto import get_random_string
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .api_permissions import IsCashier, IsDirector, IsDirectorOrCashier, IsWaiter
from .api_serializers import (
    BulkDailyStockSerializer,
    ClientOrderSerializer,
    MenuItemSerializer,
    ProductDailyStockResponseSerializer,
    ProductDailyStockSerializer,
    TableListSerializer,
    WaiterCreateSerializer,
    WaiterUpdateSerializer,
    serialize_order,
)
from .models import (
    DiningTable, MenuCategory, Order, OrderItem, Payment,
    Product, ProductDailyStock, UserProfile, Waiter,
)

User = get_user_model()

ACTIVE_ORDER_STATUSES = (Order.Status.NEW, Order.Status.ACCEPTED, Order.Status.PARTIALLY_REJECTED)


def ensure_profile(user):
    profile = getattr(user, "profile", None)
    if profile is None:
        default_role = UserProfile.Role.CASHIER if user.username.lower().startswith("kass") else UserProfile.Role.WAITER
        profile = UserProfile.objects.create(
            user=user, full_name=user.get_full_name() or user.username,
            role=default_role, phone="", shift="", experience="",
        )
    return profile


# ============================================================
# DIREKTOR — Ofitsant CRUD
# ============================================================

class DirectorWaitersView(APIView):
    permission_classes = [IsDirector]

    def get(self, request):
        waiters = User.objects.filter(
            profile__role=UserProfile.Role.WAITER
        ).select_related("profile").prefetch_related("assigned_tables")
        data = []
        for user in waiters:
            waiter = getattr(user, "waiter_profile", None)
            active = waiter.orders.filter(status__in=[Order.Status.NEW, Order.Status.ACCEPTED]).count() if waiter else 0
            rejected = waiter.orders.filter(status=Order.Status.PARTIALLY_REJECTED).count() if waiter else 0
            data.append({
                "id": user.id,
                "username": user.username,
                "full_name": user.profile.full_name,
                "phone": user.profile.phone,
                "shift": user.profile.shift,
                "experience": user.profile.experience,
                "tables": list(user.assigned_tables.order_by("number").values_list("number", flat=True)),
                "active_orders_count": active,
                "rejected_orders_count": rejected,
            })
        return Response(data)

    def post(self, request):
        serializer = WaiterCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        with transaction.atomic():
            user = User.objects.create_user(username=d["username"], password=d["password"])
            profile = UserProfile.objects.create(
                user=user, full_name=d["full_name"], role=UserProfile.Role.WAITER,
                phone=d.get("phone", ""), shift=d.get("shift", ""), experience=d.get("experience", ""),
            )
            Waiter.objects.create(
                user=user, full_name=d["full_name"],
                phone=d.get("phone", ""), shift=d.get("shift", ""), experience=d.get("experience", ""),
            )
        return Response({
            "id": user.id, "username": user.username, "full_name": profile.full_name,
            "phone": profile.phone, "shift": profile.shift, "experience": profile.experience,
        }, status=status.HTTP_201_CREATED)


class DirectorWaiterDetailView(APIView):
    permission_classes = [IsDirector]

    def patch(self, request, user_id):
        serializer = WaiterUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = get_object_or_404(User.objects.select_related("profile"), pk=user_id)
        profile = getattr(user, "profile", None)
        if not profile or profile.role != UserProfile.Role.WAITER:
            return Response({"detail": "Bu foydalanuvchi ofitsant emas."}, status=400)
        d = serializer.validated_data
        if "password" in d:
            user.set_password(d.pop("password"))
            user.save(update_fields=["password"])
        for field in ("full_name", "phone", "shift", "experience"):
            if field in d:
                setattr(profile, field, d[field])
        profile.save()
        waiter = getattr(user, "waiter_profile", None)
        if waiter:
            for field in ("full_name", "phone", "shift", "experience"):
                if field in d:
                    setattr(waiter, field, d[field])
            waiter.save()
        return Response({
            "id": user.id, "username": user.username, "full_name": profile.full_name,
            "phone": profile.phone, "shift": profile.shift, "experience": profile.experience,
        })

    def delete(self, request, user_id):
        user = get_object_or_404(User, pk=user_id)
        profile = getattr(user, "profile", None)
        if not profile or profile.role != UserProfile.Role.WAITER:
            return Response({"detail": "Bu foydalanuvchi ofitsant emas."}, status=400)
        user.is_active = False
        user.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)


# ============================================================
# DIREKTOR — Hisobotlar
# ============================================================

class RevenueReportView(APIView):
    permission_classes = [IsDirector]

    def get(self, request):
        period = request.query_params.get("period", "daily")
        today = timezone.localdate()
        if period == "weekly":
            start = today - timedelta(days=today.weekday())
        elif period == "monthly":
            start = today.replace(day=1)
        else:
            start = today

        payments = Payment.objects.filter(paid_at__date__gte=start, paid_at__date__lte=today)
        cash = payments.filter(payment_method=Payment.Method.CASH).aggregate(t=Sum("amount"))["t"] or Decimal("0")
        card = payments.filter(payment_method=Payment.Method.CARD).aggregate(t=Sum("amount"))["t"] or Decimal("0")
        mixed = payments.filter(payment_method=Payment.Method.MIXED).aggregate(t=Sum("amount"))["t"] or Decimal("0")

        daily_breakdown = []
        current = start
        while current <= today:
            day_payments = payments.filter(paid_at__date=current)
            day_cash = day_payments.filter(payment_method=Payment.Method.CASH).aggregate(t=Sum("amount"))["t"] or Decimal("0")
            day_card = day_payments.filter(payment_method=Payment.Method.CARD).aggregate(t=Sum("amount"))["t"] or Decimal("0")
            day_mixed = day_payments.filter(payment_method=Payment.Method.MIXED).aggregate(t=Sum("amount"))["t"] or Decimal("0")
            daily_breakdown.append({
                "date": current.isoformat(), "cash": day_cash, "card": day_card,
                "mixed": day_mixed, "total": day_cash + day_card + day_mixed,
            })
            current += timedelta(days=1)

        return Response({
            "period": period, "start_date": start.isoformat(), "end_date": today.isoformat(),
            "totals": {"cash": cash, "card": card, "mixed": mixed, "total": cash + card + mixed},
            "daily_breakdown": daily_breakdown,
        })


class WaiterReportView(APIView):
    permission_classes = [IsDirector]

    def get(self, request):
        period = request.query_params.get("period", "daily")
        today = timezone.localdate()
        if period == "weekly":
            start = today - timedelta(days=today.weekday())
        elif period == "monthly":
            start = today.replace(day=1)
        else:
            start = today

        waiters = User.objects.filter(profile__role=UserProfile.Role.WAITER).select_related("profile")
        data = []
        for user in waiters:
            waiter = getattr(user, "waiter_profile", None)
            if not waiter:
                continue
            orders_in_period = waiter.orders.filter(created_at__date__gte=start, created_at__date__lte=today)
            sold = orders_in_period.filter(status=Order.Status.COMPLETED).count()
            rejected = orders_in_period.filter(status=Order.Status.PARTIALLY_REJECTED).count()
            cancelled = orders_in_period.filter(status=Order.Status.CANCELLED).count()
            revenue = Payment.objects.filter(
                order__waiter=waiter, paid_at__date__gte=start, paid_at__date__lte=today,
            ).aggregate(t=Sum("amount"))["t"] or Decimal("0")
            data.append({
                "id": user.id, "full_name": user.profile.full_name,
                "sold_orders": sold, "rejected_orders": rejected,
                "cancelled_orders": cancelled, "revenue": revenue,
            })
        return Response({"period": period, "waiters": data})


# ============================================================
# DIREKTOR — QR kod
# ============================================================

class TableQRCodeView(APIView):
    permission_classes = [IsDirector]

    def get(self, request, table_id):
        table = get_object_or_404(DiningTable, pk=table_id)
        base_url = request.query_params.get("base_url", request.build_absolute_uri("/"))
        qr_url = f"{base_url.rstrip('/')}/api/v1/public/menu/{table.qr_token}"
        img = qrcode.make(qr_url, box_size=10, border=2)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        response = HttpResponse(buf.getvalue(), content_type="image/png")
        response["Content-Disposition"] = f'inline; filename="table_{table.number}_qr.png"'
        return response


# ============================================================
# KASSIR — Kunlik sig'im
# ============================================================

class DailyStockView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [permissions.IsAuthenticated()]
        return [IsCashier()]

    def get(self, request):
        today = timezone.localdate()
        stocks = ProductDailyStock.objects.filter(date=today).select_related("product")
        products = Product.objects.filter(is_active=True).select_related("category")
        stock_map = {s.product_id: s for s in stocks}
        data = []
        for product in products:
            stock = stock_map.get(product.id)
            data.append({
                "product_id": product.id, "product_name": product.name,
                "category_name": product.category.name if product.category else None,
                "price": product.price,
                "initial_quantity": stock.initial_quantity if stock else None,
                "remaining_quantity": stock.remaining_quantity if stock else None,
                "is_set": stock is not None,
            })
        return Response(data)

    def post(self, request):
        serializer = BulkDailyStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        today = timezone.localdate()
        results = []
        for item in serializer.validated_data["stocks"]:
            stock, created = ProductDailyStock.objects.update_or_create(
                product_id=item["product_id"], date=today,
                defaults={
                    "initial_quantity": item["initial_quantity"],
                    "remaining_quantity": item["initial_quantity"],
                    "set_by": request.user,
                },
            )
            results.append(ProductDailyStockResponseSerializer(stock).data)
        return Response(results, status=status.HTTP_200_OK)


# ============================================================
# KASSIR — Buyurtma qabul qilish
# ============================================================

class CashierAcceptOrderView(APIView):
    permission_classes = [IsCashier]

    def post(self, request, order_id):
        order = get_object_or_404(
            Order.objects.select_related("table", "waiter__user").prefetch_related("items__product"),
            pk=order_id,
        )
        if order.status != Order.Status.NEW:
            return Response({"detail": "Faqat yangi buyurtmalarni qabul qilish mumkin."}, status=400)
        order.items.filter(status=OrderItem.Status.PENDING).update(status=OrderItem.Status.ACCEPTED)
        order.status = Order.Status.ACCEPTED
        order.save(update_fields=["status", "updated_at"])
        if order.waiter and order.waiter.user_id:
            order.table.assigned_waiters.add(order.waiter.user)
        order.refresh_from_db()
        return Response(serialize_order(order))


class CashierPendingOrdersView(APIView):
    permission_classes = [IsCashier]

    def get(self, request):
        orders = Order.objects.filter(
            status__in=[Order.Status.NEW, Order.Status.ACCEPTED]
        ).select_related("table", "waiter__user", "waiter__user__profile").prefetch_related("items__product").order_by("created_at")
        return Response([serialize_order(o) for o in orders])


# ============================================================
# MIJOZ — QR menyu va o'z-o'ziga xizmat
# ============================================================

class PublicMenuView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, qr_token):
        table = get_object_or_404(DiningTable, qr_token=qr_token)
        categories = MenuCategory.objects.all()
        products = Product.objects.filter(is_active=True).select_related("category")
        today = timezone.localdate()
        stocks = {s.product_id: s for s in ProductDailyStock.objects.filter(date=today)}
        cat_data = []
        for cat in categories:
            items = []
            for p in products:
                if p.category_id != cat.id:
                    continue
                stock = stocks.get(p.id)
                remaining = stock.remaining_quantity if stock else None
                is_available = True
                if remaining is not None and remaining <= 0:
                    is_available = False
                items.append({
                    "id": p.id, "name": p.name, "description": p.description,
                    "price": p.price, "is_rejectable": p.is_rejectable,
                    "remaining": remaining, "is_available": is_available,
                    "image_url": request.build_absolute_uri(p.image.url) if p.image else None,
                })
            cat_data.append({"id": cat.id, "name": cat.name, "items": items})
        return Response({
            "table": {"id": table.id, "number": table.number},
            "categories": cat_data,
        })


class PublicClientOrderView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, qr_token):
        table = get_object_or_404(DiningTable, qr_token=qr_token)
        serializer = ClientOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        today = timezone.localdate()

        with transaction.atomic():
            external_id = f"CLIENT-{table.number}-{get_random_string(16)}"
            order = Order.objects.create(
                external_id=external_id, waiter=None, table=table,
                note=d.get("note", ""), status=Order.Status.NEW,
                order_source=Order.OrderSource.CLIENT, client_name=d["client_name"],
            )
            for item in d["items"]:
                product = get_object_or_404(Product, pk=item["menu_item_id"], is_active=True)
                remaining = product.get_today_remaining()
                if remaining is not None and remaining < item["quantity"]:
                    raise Http404(f"{product.name} sig'imi yetarli emas. Qolgan: {remaining}")
                OrderItem.objects.create(
                    order=order, product=product, quantity=item["quantity"],
                    note=item.get("note", ""),
                )
                stock = ProductDailyStock.objects.filter(product=product, date=today).first()
                if stock:
                    stock.remaining_quantity = max(0, stock.remaining_quantity - item["quantity"])
                    stock.save(update_fields=["remaining_quantity", "updated_at"])

        return Response({
            "id": order.id, "external_id": order.external_id,
            "table_number": table.number, "client_name": order.client_name,
            "status": "active", "total_amount": order.total_amount,
        }, status=status.HTTP_201_CREATED)


class PublicOrderStatusView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, order_id):
        order = get_object_or_404(
            Order.objects.select_related("table").prefetch_related("items__product"),
            pk=order_id, order_source=Order.OrderSource.CLIENT,
        )
        return Response(serialize_order(order))


# ============================================================
# OFITSANT — Barcha stollar ko'rish
# ============================================================

class WaiterAllTablesView(APIView):
    permission_classes = [IsWaiter]

    def get(self, request):
        tables = DiningTable.objects.prefetch_related("assigned_waiters__profile").all()
        return Response([
            TableListSerializer(t, context={"include_waiters": True}).data for t in tables
        ])


# ============================================================
# DIREKTOR — Ofitsant batafsil hisoboti (qaysi taomlar)
# ============================================================

class WaiterDetailReportView(APIView):
    """Har bir ofitsantning sotgan/qaytargan buyurtmalari va qaysi taomligi."""
    permission_classes = [IsDirector]

    def get(self, request, user_id):
        period = request.query_params.get("period", "daily")
        today = timezone.localdate()
        if period == "weekly":
            start = today - timedelta(days=today.weekday())
        elif period == "monthly":
            start = today.replace(day=1)
        else:
            start = today

        user = get_object_or_404(User.objects.select_related("profile"), pk=user_id)
        waiter = getattr(user, "waiter_profile", None)
        if not waiter:
            return Response({"detail": "Bu foydalanuvchi ofitsant emas."}, status=400)

        orders_qs = waiter.orders.filter(
            created_at__date__gte=start, created_at__date__lte=today
        ).select_related("table").prefetch_related("items__product")

        sold_items = {}
        rejected_items = {}
        orders_data = []

        for order in orders_qs:
            order_info = {
                "id": order.id, "table_number": order.table.number,
                "status": order.status, "created_at": order.created_at,
                "total": order.total_amount,
            }
            orders_data.append(order_info)
            for item in order.items.all():
                key = item.product.name
                if item.status == OrderItem.Status.REJECTED:
                    rejected_items.setdefault(key, {"quantity": 0, "total": Decimal("0")})
                    rejected_items[key]["quantity"] += item.quantity
                    rejected_items[key]["total"] += item.line_total
                else:
                    sold_items.setdefault(key, {"quantity": 0, "total": Decimal("0")})
                    sold_items[key]["quantity"] += item.quantity
                    sold_items[key]["total"] += item.line_total

        revenue = Payment.objects.filter(
            order__waiter=waiter, paid_at__date__gte=start, paid_at__date__lte=today,
        ).aggregate(t=Sum("amount"))["t"] or Decimal("0")

        return Response({
            "waiter": {"id": user.id, "full_name": user.profile.full_name},
            "period": period,
            "total_orders": len(orders_data),
            "revenue": revenue,
            "sold_items": [{"name": k, **v} for k, v in sold_items.items()],
            "rejected_items": [{"name": k, **v} for k, v in rejected_items.items()],
            "orders": orders_data,
        })


# ============================================================
# KASSIR — Stol hisobi va chek
# ============================================================

class CashierTableBillView(APIView):
    """Stol raqami bo'yicha hisobni olish va chek ma'lumotlari."""
    permission_classes = [IsDirectorOrCashier]

    def get(self, request, table_id):
        table = get_object_or_404(DiningTable, pk=table_id)
        active_orders = Order.objects.filter(
            table=table, status__in=ACTIVE_ORDER_STATUSES
        ).select_related("waiter__user__profile").prefetch_related("items__product").order_by("created_at")

        items_summary = {}
        grand_total = Decimal("0")
        orders_list = []

        for order in active_orders:
            order_items = []
            for item in order.items.all():
                if item.status == OrderItem.Status.REJECTED:
                    continue
                line = item.line_total
                grand_total += line
                order_items.append({
                    "product_name": item.product.name,
                    "quantity": item.quantity,
                    "unit_price": item.product.price,
                    "line_total": line,
                    "note": item.note,
                })
                key = item.product.name
                items_summary.setdefault(key, {"quantity": 0, "unit_price": item.product.price, "total": Decimal("0")})
                items_summary[key]["quantity"] += item.quantity
                items_summary[key]["total"] += line

            source = order.client_name if order.order_source == Order.OrderSource.CLIENT else (
                order.waiter.full_name if order.waiter else "—"
            )
            orders_list.append({
                "id": order.id, "source": source,
                "order_source": order.order_source,
                "items": order_items,
            })

        return Response({
            "table": {"id": table.id, "number": table.number},
            "status": table.current_status,
            "orders_count": len(orders_list),
            "grand_total": grand_total,
            "items_summary": [{"name": k, **v} for k, v in items_summary.items()],
            "orders": orders_list,
        })


class CashierCloseTableView(APIView):
    """Stol hisobini yopish — barcha aktiv buyurtmalarni yakunlash va to'lov yaratish."""
    permission_classes = [IsCashier]

    def post(self, request, table_id):
        table = get_object_or_404(DiningTable, pk=table_id)
        payment_method = request.data.get("payment_method", "cash")
        if payment_method not in dict(Payment.Method.choices):
            return Response({"detail": "Noto'g'ri to'lov usuli."}, status=400)

        active_orders = Order.objects.filter(
            table=table, status__in=ACTIVE_ORDER_STATUSES
        ).prefetch_related("items__product")

        if not active_orders.exists():
            return Response({"detail": "Bu stolda aktiv buyurtma yo'q."}, status=400)

        total = Decimal("0")
        payments_created = []

        with transaction.atomic():
            for order in active_orders:
                order_total = sum(
                    (item.line_total for item in order.items.all()
                    if item.status != OrderItem.Status.REJECTED),
                    Decimal("0")
                )
                total += order_total
                if not hasattr(order, "payment"):
                    payment = Payment.objects.create(
                        order=order, payment_method=payment_method,
                        amount=order_total, cashier=request.user,
                    )
                    payments_created.append(payment.id)
                order.status = Order.Status.COMPLETED
                order.save(update_fields=["status", "updated_at"])

            table.assigned_waiters.clear()

        return Response({
            "table_number": table.number,
            "total_amount": total,
            "payment_method": payment_method,
            "orders_closed": active_orders.count(),
            "payments_created": payments_created,
        })


# ============================================================
# MIJOZ — Rad etiladigan taomni o'z buyurtmasidan rad etish
# ============================================================

class PublicClientRejectItemView(APIView):
    """Mijoz o'z buyurtmasidagi rad etiladigan taomni rad etishi."""
    permission_classes = [permissions.AllowAny]

    def post(self, request, order_id, item_id):
        order = get_object_or_404(
            Order, pk=order_id, order_source=Order.OrderSource.CLIENT
        )
        if order.status not in (Order.Status.NEW, Order.Status.ACCEPTED):
            return Response({"detail": "Bu buyurtmani o'zgartirish mumkin emas."}, status=400)

        item = get_object_or_404(OrderItem, pk=item_id, order=order)

        if not item.product.is_rejectable:
            return Response({"detail": "Bu taomni rad etish mumkin emas."}, status=400)

        if item.status == OrderItem.Status.REJECTED:
            return Response({"detail": "Bu taom allaqachon rad etilgan."}, status=400)

        item.status = OrderItem.Status.REJECTED
        item.rejection_reason = request.data.get("reason", "Mijoz tomonidan rad etildi")
        item.save(update_fields=["status", "rejection_reason"])

        # Return remaining stock
        today = timezone.localdate()
        stock = ProductDailyStock.objects.filter(product=item.product, date=today).first()
        if stock:
            stock.remaining_quantity += item.quantity
            stock.save(update_fields=["remaining_quantity", "updated_at"])

        # Check if all items rejected
        remaining = order.items.exclude(status=OrderItem.Status.REJECTED).count()
        if remaining == 0:
            order.status = Order.Status.CANCELLED
            order.status_reason = "Barcha taomlar rad etildi"
            order.save(update_fields=["status", "status_reason", "updated_at"])
        else:
            has_rejected = order.items.filter(status=OrderItem.Status.REJECTED).exists()
            if has_rejected and order.status != Order.Status.PARTIALLY_REJECTED:
                order.status = Order.Status.PARTIALLY_REJECTED
                order.save(update_fields=["status", "updated_at"])

        return Response({"detail": "Taom rad etildi.", "order_status": order.status})

