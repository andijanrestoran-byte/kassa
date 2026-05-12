"""Add qr_token, is_rejectable, image, order_source, client_name, note, ProductDailyStock."""

import secrets

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def populate_qr_tokens(apps, schema_editor):
    """Mavjud stollar uchun unikal QR tokenlar yaratish."""
    DiningTable = apps.get_model("orders", "DiningTable")
    for table in DiningTable.objects.all():
        table.qr_token = secrets.token_hex(16)
        table.save(update_fields=["qr_token"])


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("orders", "0005_seed_default_tables_and_menu"),
    ]

    operations = [
        # --- DiningTable: qr_token (dastlab unique emas) ---
        migrations.AddField(
            model_name="diningtable",
            name="qr_token",
            field=models.CharField(
                blank=True,
                default="",
                help_text="QR kod uchun unikal token. Avtomatik yaratiladi.",
                max_length=32,
            ),
            preserve_default=False,
        ),
        # Mavjud stollar uchun tokenlar to'ldirish
        migrations.RunPython(populate_qr_tokens, migrations.RunPython.noop),
        # Endi unique qilish
        migrations.AlterField(
            model_name="diningtable",
            name="qr_token",
            field=models.CharField(
                blank=True,
                help_text="QR kod uchun unikal token. Avtomatik yaratiladi.",
                max_length=32,
                unique=True,
            ),
        ),
        # --- Product: is_rejectable ---
        migrations.AddField(
            model_name="product",
            name="is_rejectable",
            field=models.BooleanField(
                default=True,
                help_text="Rad etish mumkinmi? False bo'lsa, mijoz/kassir rad eta olmaydi.",
            ),
        ),
        # --- Product: image ---
        migrations.AddField(
            model_name="product",
            name="image",
            field=models.ImageField(
                blank=True,
                help_text="Mahsulot rasmi.",
                null=True,
                upload_to="products/",
            ),
        ),
        # --- Order: order_source ---
        migrations.AddField(
            model_name="order",
            name="order_source",
            field=models.CharField(
                choices=[("waiter", "Ofitsant"), ("client", "Mijoz (o'z-o'ziga xizmat)")],
                default="waiter",
                max_length=20,
            ),
        ),
        # --- Order: client_name ---
        migrations.AddField(
            model_name="order",
            name="client_name",
            field=models.CharField(
                blank=True,
                help_text="Mijoz o'z-o'ziga xizmat berganida ismi.",
                max_length=100,
            ),
        ),
        # --- Order: waiter nullable ---
        migrations.AlterField(
            model_name="order",
            name="waiter",
            field=models.ForeignKey(
                blank=True,
                help_text="Mijoz o'z-o'ziga xizmat bersa null bo'ladi.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="orders",
                to="orders.waiter",
            ),
        ),
        # --- OrderItem: note ---
        migrations.AddField(
            model_name="orderitem",
            name="note",
            field=models.TextField(
                blank=True,
                help_text="Ofitsant yoki mijoz izohi (masalan: tuzsiz, achchiqsiz)",
            ),
        ),
        # --- ProductDailyStock ---
        migrations.CreateModel(
            name="ProductDailyStock",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(default=django.utils.timezone.localdate)),
                ("initial_quantity", models.PositiveIntegerField(help_text="Boshlang'ich sig'im (kunning boshida)")),
                ("remaining_quantity", models.PositiveIntegerField(help_text="Qolgan sig'im")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="daily_stocks",
                        to="orders.product",
                    ),
                ),
                (
                    "set_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="stock_entries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Kunlik sig'im",
                "verbose_name_plural": "Kunlik sig'imlar",
                "ordering": ["-date", "product__name"],
                "unique_together": {("product", "date")},
            },
        ),
    ]
