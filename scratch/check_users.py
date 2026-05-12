import os
import sys
import django

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()

print("Bazada mavjud foydalanuvchilar:")
for user in User.objects.all():
    profile = getattr(user, 'profile', None)
    role = profile.role if profile else "No Profile"
    print(f"- Username: {user.username}, Active: {user.is_active}, Role: {role}, Has Password: {user.has_usable_password()}")
