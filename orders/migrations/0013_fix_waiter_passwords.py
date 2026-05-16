"""Seed ofitsant parollarini tuzatish.

0010_seed_mobile_users prod DB'da allaqachon "applied" bo'lgani uchun
uning o'zgartirilgan mazmuni qayta ishlamaydi -> azizbek/javohir login
qila olmaydi (401). Bu YANGI migratsiya deployda bir marta ishlab,
ofitsant akkauntlarini ma'lum parol bilan tiklaydi.
"""

import sys

from django.contrib.auth.hashers import make_password
from django.db import migrations


WAITERS = [
    {"username": "azizbek", "password": "12345", "full_name": "Azizbek Abdullayev"},
    {"username": "javohir", "password": "11111", "full_name": "Javohir Javohirov"},
]


def fix_waiter_passwords(apps, schema_editor):
    if "test" in sys.argv:
        return
    User = apps.get_model("auth", "User")
    UserProfile = apps.get_model("orders", "UserProfile")
    Waiter = apps.get_model("orders", "Waiter")

    for data in WAITERS:
        user, _ = User.objects.update_or_create(
            username=data["username"],
            defaults={"is_staff": False, "is_active": True},
        )
        user.password = make_password(data["password"])
        user.save(update_fields=["password"])

        UserProfile.objects.update_or_create(
            user=user,
            defaults={
                "full_name": data["full_name"],
                "role": "waiter",
                "phone": "",
                "shift": "",
                "experience": "",
            },
        )
        Waiter.objects.update_or_create(
            user=user,
            defaults={
                "full_name": data["full_name"],
                "phone": "",
                "shift": "",
                "experience": "",
            },
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0012_order_public_token"),
    ]

    operations = [
        migrations.RunPython(fix_waiter_passwords, noop_reverse),
    ]
