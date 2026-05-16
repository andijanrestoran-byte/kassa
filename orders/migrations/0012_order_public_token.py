import secrets

from django.db import migrations, models


def populate_public_tokens(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    for order in Order.objects.filter(public_token__isnull=True):
        order.public_token = secrets.token_hex(16)
        order.save(update_fields=["public_token"])


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0011_seed_tables_and_menu"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="public_token",
            field=models.CharField(
                blank=True,
                help_text="Public mijoz endpointlari uchun maxfiy token.",
                max_length=32,
                null=True,
                unique=True,
            ),
        ),
        migrations.RunPython(populate_public_tokens, migrations.RunPython.noop),
    ]
