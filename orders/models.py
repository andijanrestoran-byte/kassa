import secrets
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class UserProfile(models.Model):
    class Role(models.TextChoices):
        WAITER = "waiter", "Waiter"
        DIRECTOR = "director", "Director"
        CASHIER = "cashier", "Cashier"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    full_name = models.CharField(max_length=150)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.WAITER)
    phone = models.CharField(max_length=30, blank=True)
    shift = models.CharField(max_length=60, blank=True)
    experience = models.CharField(max_length=60, blank=True)

    class Meta:
        verbose_name = "Foydalanuvchi profili"
        verbose_name_plural = "Foydalanuvchi profillari"

    def __str__(self) -> str:
        return f"{self.full_name} ({self.role})"


class Waiter(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="waiter_profile",
        null=True,
        blank=True,
    )
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=30, blank=True)
    shift = models.CharField(max_length=60, blank=True)
    experience = models.CharField(max_length=60, blank=True)

    class Meta:
        ordering = ["full_name"]
        verbose_name = "Ofitsant"
        verbose_name_plural = "Ofitsantlar"

    def __str__(self) -> str:
        return self.full_name


class DiningTable(models.Model):
    class Status(models.TextChoices):
        FREE = "free", "Bo'sh"
        BUSY = "busy", "Band"
        ASSIGNED = "assigned", "Biriktirilgan"

    number = models.PositiveSmallIntegerField(unique=True)
    zone = models.CharField(max_length=100, blank=True)
    seats = models.PositiveSmallIntegerField(default=4)
    location = models.CharField(max_length=150, blank=True)
    qr_token = models.CharField(
        max_length=32,
        unique=True,
        blank=True,
        help_text="QR kod uchun unikal token. Avtomatik yaratiladi.",
    )
    assigned_waiters = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="assigned_tables",
    )

    class Meta:
        ordering = ["number"]
        verbose_name = "Stol"
        verbose_name_plural = "Stollar"

    def __str__(self) -> str:
        return f"Stol #{self.number}"

    def save(self, *args, **kwargs):
        if not self.qr_token:
            self.qr_token = secrets.token_hex(16)
        super().save(*args, **kwargs)

    @property
    def current_status(self):
        if self.orders.filter(status__in=[Order.Status.NEW, Order.Status.ACCEPTED]).exists():
            return self.Status.BUSY
        if self.assigned_waiters.exists():
            return self.Status.ASSIGNED
        return self.Status.FREE


class MenuCategory(models.Model):
    name = models.CharField(max_length=120)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Menu kategoriyasi"
        verbose_name_plural = "Menu kategoriyalari"

    def __str__(self) -> str:
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=150)
    category = models.ForeignKey(
        MenuCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="items",
    )
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    is_rejectable = models.BooleanField(
        default=True,
        help_text="Rad etish mumkinmi? False bo'lsa, mijoz/kassir rad eta olmaydi.",
    )
    image = models.ImageField(
        upload_to="products/",
        blank=True,
        null=True,
        help_text="Mahsulot rasmi.",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Mahsulot"
        verbose_name_plural = "Mahsulotlar"

    def __str__(self) -> str:
        return self.name

    def get_today_remaining(self):
        """Bugungi qolgan sig'imni qaytaradi. None = sig'im belgilanmagan (cheksiz)."""
        today = timezone.localdate()
        stock = self.daily_stocks.filter(date=today).first()
        if stock is None:
            return None
        return stock.remaining_quantity


class ProductDailyStock(models.Model):
    """Kassir har kuni ovqat sig'imini belgilaydi."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="daily_stocks",
    )
    date = models.DateField(default=timezone.localdate)
    initial_quantity = models.PositiveIntegerField(
        help_text="Boshlang'ich sig'im (kunning boshida)",
    )
    remaining_quantity = models.PositiveIntegerField(
        help_text="Qolgan sig'im",
    )
    set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="stock_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("product", "date")
        ordering = ["-date", "product__name"]
        verbose_name = "Kunlik sig'im"
        verbose_name_plural = "Kunlik sig'imlar"

    def __str__(self) -> str:
        return f"{self.product.name} — {self.date} — {self.remaining_quantity}/{self.initial_quantity}"


class Order(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Yangi"
        ACCEPTED = "accepted", "Qabul qilingan"
        PARTIALLY_REJECTED = "partially_rejected", "Qisman rad etilgan"
        COMPLETED = "completed", "Yakunlangan"
        CANCELLED = "cancelled", "Bekor qilingan"

    class OrderSource(models.TextChoices):
        WAITER = "waiter", "Ofitsant"
        CLIENT = "client", "Mijoz (o'z-o'ziga xizmat)"

    external_id = models.CharField(
        max_length=64,
        unique=True,
        help_text="Mobil platformadagi buyurtma identifikatori.",
    )
    waiter = models.ForeignKey(
        Waiter,
        on_delete=models.PROTECT,
        related_name="orders",
        null=True,
        blank=True,
        help_text="Mijoz o'z-o'ziga xizmat bersa null bo'ladi.",
    )
    table = models.ForeignKey(DiningTable, on_delete=models.PROTECT, related_name="orders")
    bill_number = models.PositiveSmallIntegerField(
        default=1,
        help_text="Stoldagi shot raqami (1-10). Bitta stolda bir nechta shot bo'lishi mumkin.",
    )
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.NEW)
    note = models.TextField(blank=True)
    status_reason = models.CharField(max_length=255, blank=True)
    order_source = models.CharField(
        max_length=20,
        choices=OrderSource.choices,
        default=OrderSource.WAITER,
    )
    client_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Mijoz o'z-o'ziga xizmat berganida ismi.",
    )
    public_token = models.CharField(
        max_length=32,
        unique=True,
        null=True,
        blank=True,
        help_text="Public mijoz endpointlari uchun maxfiy token.",
    )
    kitchen_printed = models.BooleanField(
        default=False,
        help_text="Oshxona cheki avtomatik chop etilgan-etilmagani.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Buyurtma"
        verbose_name_plural = "Buyurtmalar"

    def __str__(self) -> str:
        source = self.client_name if self.order_source == self.OrderSource.CLIENT else str(self.waiter or "—")
        return f"{self.external_id} / {source} / {self.table}"

    def save(self, *args, **kwargs):
        if not self.public_token:
            self.public_token = secrets.token_hex(16)
        super().save(*args, **kwargs)

    @property
    def total_amount(self):
        return sum((item.line_total for item in self.items.all()), Decimal("0"))

    @property
    def payable_amount(self):
        return sum(
            (item.line_total for item in self.items.all() if item.status != OrderItem.Status.REJECTED),
            Decimal("0"),
        )


class OrderItem(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Kutilmoqda"
        ACCEPTED = "accepted", "Qabul qilingan"
        REJECTED = "rejected", "Rad etilgan"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="order_items")
    quantity = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.CharField(max_length=255, blank=True)
    note = models.TextField(blank=True, help_text="Ofitsant yoki mijoz izohi (masalan: tuzsiz, achchiqsiz)")

    class Meta:
        verbose_name = "Buyurtma mahsuloti"
        verbose_name_plural = "Buyurtma mahsulotlari"

    def __str__(self) -> str:
        return f"{self.product} x {self.quantity}"

    @property
    def line_total(self):
        return self.product.price * self.quantity


class ApiToken(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_tokens")
    key = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "API token"
        verbose_name_plural = "API tokenlar"

    def __str__(self) -> str:
        return f"{self.user} / {self.key[:8]}"

    @classmethod
    def generate_key(cls) -> str:
        return secrets.token_hex(32)


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        CARD = "card", "Card"
        MIXED = "mixed", "Mixed"

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="payment")
    payment_method = models.CharField(max_length=20, choices=Method.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payments")
    paid_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-paid_at"]
        verbose_name = "To'lov"
        verbose_name_plural = "To'lovlar"

    def __str__(self) -> str:
        return f"{self.order_id} / {self.payment_method} / {self.amount}"


class Shift(models.Model):
    """Kassir kunlik smenasi. Smena ochilmaguncha buyurtma qabul
    qilinmaydi va kunlik portsiya kiritilmaydi."""

    date = models.DateField(unique=True, default=timezone.localdate)
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="opened_shifts",
    )
    opened_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
        verbose_name = "Smena"
        verbose_name_plural = "Smenalar"

    def __str__(self) -> str:
        return f"Smena {self.date}"

    @classmethod
    def is_open(cls, day=None) -> bool:
        day = day or timezone.localdate()
        return cls.objects.filter(date=day).exists()
