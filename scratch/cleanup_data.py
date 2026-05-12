import os
import sys
import django

# Loyiha ildiz papkasini PYTHONPATH ga qo'shamiz
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from orders.models import (
    DiningTable, MenuCategory, Order, OrderItem, 
    Payment, Product, ProductDailyStock, UserProfile, Waiter
)

User = get_user_model()

def cleanup():
    print("Tozalash boshlandi...")
    
    # 1. Buyurtmalar va to'lovlarni o'chirish
    print("Buyurtmalar va to'lovlar o'chirilmoqda...")
    Order.objects.all().delete()
    Payment.objects.all().delete()
    ProductDailyStock.objects.all().delete()
    
    # 2. Menyu va kategoriyalarni o'chirish
    print("Menyu va kategoriyalar o'chirilmoqda...")
    Product.objects.all().delete()
    MenuCategory.objects.all().delete()
    
    # 3. Stollarni o'chirish
    print("Stollar o'chirilmoqda...")
    DiningTable.objects.all().delete()
    
    # 4. Foydalanuvchilarni tozalash (faqat namunaviy ma'lumotlarni)
    # Biz foydalanuvchilarning o'zini o'chirmaymiz, faqat ularga biriktirilgan stollarni tozalaymiz
    print("Ofitsantlar va direktorlar saqlanmoqda, biriktirmalar tozalanmoqda...")
    for user in User.objects.all():
        if hasattr(user, 'assigned_tables'):
            user.assigned_tables.clear()
            
    print("Tozalash yakunlandi. Tizim ishga tushishga tayyor (toza bazada).")

if __name__ == "__main__":
    cleanup()
