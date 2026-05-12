from django.db import migrations
from django.contrib.auth.hashers import make_password


def create_staff_users(apps, schema_editor):
    User = apps.get_model("auth", "User")
    UserProfile = apps.get_model("orders", "UserProfile")
    
    # 1. Direktor yaratish
    dir_user, created = User.objects.get_or_create(
        username="director",
        defaults={
            "password": make_password("dir12345"),
            "is_staff": True
        }
    )
    if created:
        UserProfile.objects.update_or_create(
            user=dir_user,
            defaults={"role": "director", "full_name": "Asosiy Direktor"}
        )

    # 2. Ofitsant 1 yaratish
    w1_user, created = User.objects.get_or_create(
        username="waiter1",
        defaults={
            "password": make_password("waiter123"),
            "is_staff": False
        }
    )
    if created:
        UserProfile.objects.update_or_create(
            user=w1_user,
            defaults={"role": "waiter", "full_name": "Ofitsant Birinchi"}
        )

    # 3. Ofitsant 2 yaratish
    w2_user, created = User.objects.get_or_create(
        username="waiter2",
        defaults={
            "password": make_password("waiter123"),
            "is_staff": False
        }
    )
    if created:
        UserProfile.objects.update_or_create(
            user=w2_user,
            defaults={"role": "waiter", "full_name": "Ofitsant Ikkinchi"}
        )


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0007_clear_sample_data"),
    ]

    operations = [
        migrations.RunPython(create_staff_users, migrations.RunPython.noop),
    ]
