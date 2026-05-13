from django.db import migrations
from django.contrib.auth.hashers import make_password


import sys


def create_staff_users(apps, schema_editor):
    if 'test' in sys.argv:
        return
    User = apps.get_model("auth", "User")
    UserProfile = apps.get_model("orders", "UserProfile")
    
    # 1. Direktor
    dir_user, _ = User.objects.update_or_create(
        username="director",
        defaults={
            "is_staff": True,
            "is_active": True
        }
    )
    dir_user.password = make_password("dir12345")
    dir_user.save()
    
    UserProfile.objects.update_or_create(
        user=dir_user,
        defaults={"role": "director", "full_name": "Asosiy Direktor"}
    )

    # 2. Ofitsant 1
    w1_user, _ = User.objects.update_or_create(
        username="waiter1",
        defaults={
            "is_staff": False,
            "is_active": True
        }
    )
    w1_user.password = make_password("waiter123")
    w1_user.save()
    
    UserProfile.objects.update_or_create(
        user=w1_user,
        defaults={"role": "waiter", "full_name": "Ofitsant Birinchi"}
    )

    # 3. Ofitsant 2
    w2_user, _ = User.objects.update_or_create(
        username="waiter2",
        defaults={
            "is_staff": False,
            "is_active": True
        }
    )
    w2_user.password = make_password("waiter123")
    w2_user.save()
    
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
