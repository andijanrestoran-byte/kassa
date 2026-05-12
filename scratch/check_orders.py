import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from orders.models import Order

print(f"Total orders: {Order.objects.count()}")
for order in Order.objects.all()[:10]:
    print(f"ID: {order.id}, ExtID: {order.external_id}, Status: {order.status}, Source: {order.order_source}, Created: {order.created_at}")
