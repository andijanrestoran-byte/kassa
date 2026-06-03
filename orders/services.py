from decimal import Decimal

from .models import Order


ACTIVE_ORDER_STATUSES = (
    Order.Status.NEW,
    Order.Status.ACCEPTED,
    Order.Status.PARTIALLY_REJECTED,
)


def next_client_bill_number(table) -> int:
    """Mijoz QR orqali buyurtma berganda — keyingi bo'sh shot (hisob) raqami.

    Har bir mijoz (qurilma) alohida hisob bo'lib ko'rinishi uchun, stoldagi
    faol buyurtmalar band qilmagan eng kichik 1-10 raqam tanlanadi. Barchasi
    band bo'lsa (kamdan-kam), 10 dan oshib ketadi.
    """
    used = set(
        Order.objects.filter(table=table, status__in=ACTIVE_ORDER_STATUSES)
        .values_list("bill_number", flat=True)
    )
    for number in range(1, 11):
        if number not in used:
            return number
    return max(used) + 1 if used else 1


def order_total(order: Order) -> Decimal:
    return sum((item.line_total for item in order.items.all()), Decimal("0"))


def order_payable_total(order: Order) -> Decimal:
    return order.payable_amount


def table_summary(table):
    active_orders = list(
        Order.objects.filter(table=table, status__in=ACTIVE_ORDER_STATUSES)
        .select_related("waiter", "table")
        .prefetch_related("items__product")
        .order_by("bill_number", "-created_at")
    )

    shots = {}
    for order in active_orders:
        bill_number = order.bill_number
        if bill_number not in shots:
            shots[bill_number] = {
                "bill_number": bill_number,
                "orders": [],
                "total_amount": Decimal("0"),
                "items_count": 0,
                "latest_order": order,
            }
        shots[bill_number]["orders"].append(order)
        shots[bill_number]["total_amount"] += order_total(order)
        shots[bill_number]["items_count"] += order.items.count()

    shots_list = sorted(shots.values(), key=lambda item: item["bill_number"])
    total_amount_table = sum((shot["total_amount"] for shot in shots_list), Decimal("0"))
    total_items_table = sum((shot["items_count"] for shot in shots_list), 0)
    latest_order = active_orders[0] if active_orders else None

    return {
        "table": table,
        "shots": shots_list,
        "active_orders": active_orders,
        "orders_count": len(active_orders),
        "items_count": total_items_table,
        "total_amount": total_amount_table,
        "latest_order": latest_order,
    }
