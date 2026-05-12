from django.db import migrations


def clear_all_data(apps, schema_editor):
    """Barcha namunaviy ma'lumotlarni o'chirish."""
    OrderItem = apps.get_model("orders", "OrderItem")
    Order = apps.get_model("orders", "Order")
    Payment = apps.get_model("orders", "Payment")
    ProductDailyStock = apps.get_model("orders", "ProductDailyStock")
    Product = apps.get_model("orders", "Product")
    MenuCategory = apps.get_model("orders", "MenuCategory")
    DiningTable = apps.get_model("orders", "DiningTable")

    # Bog'liqliklar tartibida o'chirish
    OrderItem.objects.all().delete()
    Order.objects.all().delete()
    Payment.objects.all().delete()
    ProductDailyStock.objects.all().delete()
    Product.objects.all().delete()
    MenuCategory.objects.all().delete()
    DiningTable.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0006_add_new_fields"),
    ]

    operations = [
        migrations.RunPython(clear_all_data, migrations.RunPython.noop),
    ]
