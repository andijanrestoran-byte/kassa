from django.contrib import admin
from .models import ApiToken, DiningTable, MenuCategory, Order, OrderItem, Payment, Product, ProductDailyStock, UserProfile, Waiter


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("external_id", "waiter", "table", "status", "order_source", "client_name", "created_at")
    list_filter = ("status", "order_source", "created_at")
    search_fields = ("external_id", "waiter__full_name", "table__number", "client_name")
    inlines = [OrderItemInline]


@admin.register(Waiter)
class WaiterAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user", "phone")
    search_fields = ("full_name", "phone", "user__username")


@admin.register(DiningTable)
class DiningTableAdmin(admin.ModelAdmin):
    list_display = ("number", "zone", "seats", "location", "qr_token")
    search_fields = ("number", "zone", "location")
    filter_horizontal = ("assigned_waiters",)
    readonly_fields = ("qr_token",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "is_active", "is_rejectable")
    list_filter = ("is_active", "is_rejectable", "category")
    search_fields = ("name",)


@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "key", "created_at")
    search_fields = ("user__username", "key")


@admin.register(MenuCategory)
class MenuCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "sort_order")
    search_fields = ("name",)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "full_name", "role", "phone")
    list_filter = ("role",)
    search_fields = ("user__username", "full_name", "phone")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("order", "payment_method", "amount", "cashier", "paid_at")
    list_filter = ("payment_method", "paid_at")
    search_fields = ("order__external_id", "cashier__username")


@admin.register(ProductDailyStock)
class ProductDailyStockAdmin(admin.ModelAdmin):
    list_display = ("product", "date", "initial_quantity", "remaining_quantity", "set_by")
    list_filter = ("date",)
    search_fields = ("product__name",)
