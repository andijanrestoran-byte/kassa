from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import migrations


DEFAULT_CASHIER_USERNAME = "kassir"
DEFAULT_CASHIER_PASSWORD = "Kassir123!"


import sys


def seed_cashier_user(apps, schema_editor):
    if 'test' in sys.argv:
        return
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(app_label, model_name)
    UserProfile = apps.get_model("orders", "UserProfile")

    user, created = User.objects.get_or_create(
        username=DEFAULT_CASHIER_USERNAME,
        defaults={
            "password": make_password(DEFAULT_CASHIER_PASSWORD),
            "is_active": True,
        },
    )
    if not created:
        user.password = make_password(DEFAULT_CASHIER_PASSWORD)
        user.is_active = True
        user.save(update_fields=["password", "is_active"])

    UserProfile.objects.update_or_create(
        user=user,
        defaults={
            "full_name": "Kassir",
            "role": "cashier",
            "phone": "",
            "shift": "",
            "experience": "",
        },
    )


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0003_menucategory_diningtable_assigned_waiters_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_cashier_user, noop_reverse),
    ]
