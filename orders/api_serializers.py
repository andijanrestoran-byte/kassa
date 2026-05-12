from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Sum, Q
from django.utils import timezone
from rest_framework import serializers

from .models import DiningTable, MenuCategory, Order, OrderItem, Payment, Product, ProductDailyStock, UserProfile, Waiter

User = get_user_model()


def map_order_status(order: Order) -> str:
    if order.status == Order.Status.PARTIALLY_REJECTED:
        return "rejected"
    if order.status == Order.Status.COMPLETED:
        return "paid"
    if order.status == Order.Status.CANCELLED:
        return "cancelled"
    return "active"


def get_user_profile(user):
    return getattr(user, "profile", None)


def waiter_user_payload(waiter: Waiter):
    if waiter is None:
        return {"id": None, "username": "mijoz", "full_name": "Mijoz"}
    if waiter.user:
        profile = get_user_profile(waiter.user)
        return {
            "id": waiter.user.id,
            "username": waiter.user.username,
            "full_name": profile.full_name if profile else waiter.full_name,
        }
    return {
        "id": waiter.id,
        "username": waiter.full_name.lower().replace(" ", "_"),
        "full_name": waiter.full_name,
    }


class UserShortSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    full_name = serializers.CharField()


class UserProfileSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="user.id")
    username = serializers.CharField(source="user.username")
    full_name = serializers.CharField()
    role = serializers.CharField()
    phone = serializers.CharField()
    shift = serializers.CharField()
    experience = serializers.CharField()


class TableWaiterSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    full_name = serializers.CharField()


class TableListSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    assigned_waiters = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()

    class Meta:
        model = DiningTable
        fields = ("id", "number", "seats", "location", "status", "assigned_waiters", "qr_token")

    def get_status(self, obj):
        return obj.current_status

    def get_location(self, obj):
        return obj.location or obj.zone

    def get_assigned_waiters(self, obj):
        include_waiters = self.context.get("include_waiters", False)
        if not include_waiters:
            return []
        payload = []
        for user in obj.assigned_waiters.all():
            profile = get_user_profile(user)
            payload.append(
                {
                    "id": user.id,
                    "username": user.username,
                    "full_name": profile.full_name if profile else user.username,
                }
            )
        return payload


class TableWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiningTable
        fields = ("number", "zone", "seats", "location")


class MenuCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuCategory
        fields = ("id", "name", "sort_order")


class MenuItemSerializer(serializers.ModelSerializer):
    category_id = serializers.IntegerField(source="category.id", allow_null=True, read_only=True)
    category_name = serializers.CharField(source="category.name", allow_null=True, read_only=True)
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    remaining_today = serializers.SerializerMethodField()
    is_available = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id", "name", "category_id", "category_name", "description",
            "price", "is_active", "is_rejectable", "remaining_today",
            "is_available", "image_url",
        )

    def get_remaining_today(self, obj):
        return obj.get_today_remaining()

    def get_is_available(self, obj):
        if not obj.is_active:
            return False
        remaining = obj.get_today_remaining()
        if remaining is not None and remaining <= 0:
            return False
        return True

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None


class MenuItemWriteSerializer(serializers.ModelSerializer):
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=MenuCategory.objects.all(),
        source="category",
    )

    class Meta:
        model = Product
        fields = ("name", "category_id", "description", "price", "is_active", "is_rejectable", "image")


class OrderItemResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    menu_item_id = serializers.IntegerField()
    menu_item_name = serializers.CharField()
    quantity = serializers.IntegerField()
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    note = serializers.CharField(allow_blank=True)
    is_rejectable = serializers.BooleanField()


class OrderListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    table = serializers.DictField()
    waiter = serializers.DictField()
    status = serializers.CharField()
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    created_at = serializers.DateTimeField()
    order_source = serializers.CharField()
    client_name = serializers.CharField(allow_blank=True)


class OrderDetailSerializer(OrderListSerializer):
    note = serializers.CharField()
    reason = serializers.CharField(allow_blank=True)
    items = serializers.ListField()


class CreateOrderItemInputSerializer(serializers.Serializer):
    menu_item_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    note = serializers.CharField(allow_blank=True, required=False, default="")


class CreateOrderSerializer(serializers.Serializer):
    table_id = serializers.IntegerField()
    note = serializers.CharField(allow_blank=True, required=False, default="")
    items = CreateOrderItemInputSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("Kamida bitta mahsulot yuborilishi kerak.")
        return value


class ClientOrderSerializer(serializers.Serializer):
    """Mijoz o'z-o'ziga xizmat — auth kerak emas."""
    client_name = serializers.CharField(max_length=100)
    note = serializers.CharField(allow_blank=True, required=False, default="")
    items = CreateOrderItemInputSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("Kamida bitta mahsulot yuborilishi kerak.")
        return value


class RejectCancelSerializer(serializers.Serializer):
    reason = serializers.CharField()


class PaymentCreateSerializer(serializers.Serializer):
    order_id = serializers.IntegerField()
    payment_method = serializers.ChoiceField(choices=Payment.Method.choices)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))


class PaymentUpdateSerializer(serializers.Serializer):
    payment_method = serializers.ChoiceField(choices=Payment.Method.choices, required=False)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"), required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Kamida bitta maydon yuborilishi kerak.")
        return attrs


class PaymentListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    order_id = serializers.IntegerField()
    table_number = serializers.IntegerField()
    waiter_name = serializers.CharField()
    payment_method = serializers.CharField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    paid_at = serializers.DateTimeField()


class ProductDailyStockSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    initial_quantity = serializers.IntegerField(min_value=0)

    def validate_product_id(self, value):
        if not Product.objects.filter(pk=value, is_active=True).exists():
            raise serializers.ValidationError("Mahsulot topilmadi yoki faol emas.")
        return value


class ProductDailyStockResponseSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_price = serializers.DecimalField(source="product.price", max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = ProductDailyStock
        fields = (
            "id", "product_id", "product_name", "product_price",
            "date", "initial_quantity", "remaining_quantity",
        )


class BulkDailyStockSerializer(serializers.Serializer):
    """Kassir bir vaqtda ko'p mahsulot sig'imini belgilaydi."""
    stocks = ProductDailyStockSerializer(many=True)

    def validate_stocks(self, value):
        if not value:
            raise serializers.ValidationError("Kamida bitta mahsulot sig'imi yuborilishi kerak.")
        return value


class WaiterCreateSerializer(serializers.Serializer):
    """Direktor yangi ofitsant yaratadi."""
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(min_length=4)
    full_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=30, required=False, default="")
    shift = serializers.CharField(max_length=60, required=False, default="")
    experience = serializers.CharField(max_length=60, required=False, default="")

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Bu username allaqachon mavjud.")
        return value


class WaiterUpdateSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=150, required=False)
    phone = serializers.CharField(max_length=30, required=False)
    shift = serializers.CharField(max_length=60, required=False)
    experience = serializers.CharField(max_length=60, required=False)
    password = serializers.CharField(min_length=4, required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Kamida bitta maydon yuborilishi kerak.")
        return attrs


def serialize_order(order: Order, include_items: bool = True):
    payload = {
        "id": order.id,
        "table": {"id": order.table.id, "number": order.table.number},
        "waiter": waiter_user_payload(order.waiter),
        "status": map_order_status(order),
        "note": order.note,
        "reason": order.status_reason,
        "total_amount": Decimal(order.total_amount),
        "created_at": order.created_at,
        "order_source": order.order_source,
        "client_name": order.client_name,
    }
    if include_items:
        payload["items"] = [
            {
                "id": item.id,
                "menu_item_id": item.product.id,
                "menu_item_name": item.product.name,
                "quantity": item.quantity,
                "unit_price": item.product.price,
                "line_total": item.line_total,
                "note": item.note,
                "is_rejectable": item.product.is_rejectable,
                "status": item.status,
            }
            for item in order.items.select_related("product").all()
        ]
    return payload


def build_dashboard_summary():
    today = timezone.localdate()
    tables = DiningTable.objects.all()
    free_tables = 0
    busy_tables = 0
    assigned_tables = 0
    for table in tables:
        status = table.current_status
        if status == DiningTable.Status.FREE:
            free_tables += 1
        elif status == DiningTable.Status.BUSY:
            busy_tables += 1
        elif status == DiningTable.Status.ASSIGNED:
            assigned_tables += 1

    orders = Order.objects.all()
    today_orders = orders.filter(created_at__date=today)
    payments_today = Payment.objects.filter(paid_at__date=today)
    
    # Aggregate sums efficiently
    payment_sums = payments_today.aggregate(
        cash=Sum('amount', filter=Q(payment_method=Payment.Method.CASH)),
        card=Sum('amount', filter=Q(payment_method=Payment.Method.CARD)),
        mixed=Sum('amount', filter=Q(payment_method=Payment.Method.MIXED)),
        total=Sum('amount')
    )

    cash_today = payment_sums['cash'] or Decimal("0")
    card_today = payment_sums['card'] or Decimal("0")
    mixed_today = payment_sums['mixed'] or Decimal("0")
    total_today = payment_sums['total'] or Decimal("0")

    return {
        "tables": {
            "total": tables.count(),
            "free": free_tables,
            "busy": busy_tables,
            "assigned": assigned_tables,
        },
        "orders": {
            "active": orders.filter(status__in=[Order.Status.NEW, Order.Status.ACCEPTED]).count(),
            "rejected": orders.filter(status=Order.Status.PARTIALLY_REJECTED).count(),
            "paid_today": today_orders.filter(status=Order.Status.COMPLETED).count(),
        },
        "payments": {
            "cash_today": cash_today,
            "card_today": card_today,
            "total_today": total_today,
        },
        "staff": {
            "active_waiters": UserProfile.objects.filter(role=UserProfile.Role.WAITER, user__assigned_tables__isnull=False).distinct().count(),
        },
    }
