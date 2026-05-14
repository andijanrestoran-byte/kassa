from django.db import migrations
from django.contrib.auth.hashers import make_password


def seed_mobile_users(apps, schema_editor):
    User = apps.get_model("auth", "User")
    UserProfile = apps.get_model("orders", "UserProfile")
    Waiter = apps.get_model("orders", "Waiter")

    users_data = [
        {
            "username": "direktor",
            "password": "99999",
            "full_name": "Aziz Direktorov",
            "role": "director",
        },
        {
            "username": "azizbek",
            "password": "12345",
            "full_name": "Azizbek Abdullayev",
            "role": "waiter",
        },
        {
            "username": "javohir",
            "password": "11111",
            "full_name": "Javohir Javohirov",
            "role": "waiter",
        },
        {
            "username": "kassa",
            "password": "55555",
            "full_name": "Kassa Operator",
            "role": "cashier",
        },
    ]

    for data in users_data:
        username = data["username"]
        password = data["password"]
        full_name = data["full_name"]
        role = data["role"]

        user, _ = User.objects.update_or_create(
            username=username,
            defaults={
                "is_staff": role == "director",
                "is_active": True,
            },
        )
        user.password = make_password(password)
        user.save(update_fields=["password"])

        UserProfile.objects.update_or_create(
            user=user,
            defaults={
                "full_name": full_name,
                "role": role,
                "phone": "",
                "shift": "",
                "experience": "",
            },
        )

        if role == "waiter":
            Waiter.objects.update_or_create(
                user=user,
                defaults={
                    "full_name": full_name,
                    "phone": "",
                    "shift": "",
                    "experience": "",
                },
            )

    # Update kassir password to match mobile app
    try:
        kassir = User.objects.get(username="kassir")
        kassir.password = make_password("kassir")
        kassir.save(update_fields=["password"])
    except User.DoesNotExist:
        pass


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0009_order_bill_number"),
    ]

    operations = [
        migrations.RunPython(seed_mobile_users, noop_reverse),
    ]
