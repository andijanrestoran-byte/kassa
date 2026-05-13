import json
from decimal import Decimal
from functools import wraps

from django.contrib.auth import authenticate
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from .models import DiningTable, MenuCategory, Order, OrderItem, Product, UserProfile, Waiter

ACTIVE_ORDER_STATUSES = (
    Order.Status.NEW,
    Order.Status.ACCEPTED,
    Order.Status.PARTIALLY_REJECTED,
)


def _order_total(order: Order) -> Decimal:
    return sum((item.line_total for item in order.items.all()), Decimal("0"))


def _table_summary(table: DiningTable):
    active_orders = list(
        Order.objects.filter(table=table, status__in=ACTIVE_ORDER_STATUSES)
        .select_related("waiter", "table")
        .prefetch_related("items__product")
        .order_by("bill_number", "-created_at")
    )
    
    # Guruhlash
    shots = {}
    for order in active_orders:
        bn = order.bill_number
        if bn not in shots:
            shots[bn] = {
                "bill_number": bn,
                "orders": [],
                "total_amount": Decimal("0"),
                "items_count": 0,
                "latest_order": order,
            }
        shots[bn]["orders"].append(order)
        shots[bn]["total_amount"] += _order_total(order)
        shots[bn]["items_count"] += order.items.count()

    # Ro'yxat ko'rinishida (bill_number bo'yicha tartiblangan)
    shots_list = sorted(shots.values(), key=lambda x: x["bill_number"])

    total_amount_table = sum((s["total_amount"] for s in shots_list), Decimal("0"))
    total_items_table = sum((s["items_count"] for s in shots_list))
    
    return {
        "table": table,
        "shots": shots_list,
        "active_orders": active_orders, # Backwards compatibility for templates that expect this
        "orders_count": len(active_orders),
        "items_count": total_items_table,
        "total_amount": total_amount_table,
    }


def _base_context():
    active_orders = Order.objects.filter(status__in=ACTIVE_ORDER_STATUSES)
    return {
        "active_orders_count": active_orders.count(),
        "new_orders_count": active_orders.filter(status=Order.Status.NEW).count(),
        "accepted_orders_count": active_orders.filter(status=Order.Status.ACCEPTED).count(),
        "rejected_orders_count": active_orders.filter(status=Order.Status.PARTIALLY_REJECTED).count(),
    }


def _attach_order_to_table(order: Order):
    if order.waiter.user_id:
        order.table.assigned_waiters.add(order.waiter.user)


@require_GET
@login_required
def dashboard(request: HttpRequest):
    context = {
        **_base_context(),
        "tables_count": DiningTable.objects.count(),
    }
    return render(request, "orders/dashboard.html", context)


@require_GET
@login_required
def orders_list(request: HttpRequest):
    orders = (
        Order.objects.filter(status__in=ACTIVE_ORDER_STATUSES)
        .select_related("waiter", "table")
        .prefetch_related("items__product")
    )
    context = {
        **_base_context(),
        "orders": orders,
    }
    return render(request, "orders/orders_list.html", context)


@require_GET
@login_required
def rejected_orders(request: HttpRequest):
    rejected = (
        Order.objects.filter(status=Order.Status.PARTIALLY_REJECTED)
        .select_related("waiter", "table")
        .prefetch_related("items__product")
    )
    context = {
        **_base_context(),
        "rejected_orders": rejected,
    }
    return render(request, "orders/rejected_orders.html", context)


@require_GET
@login_required
def tables_overview(request: HttpRequest):
    tables = [_table_summary(table) for table in DiningTable.objects.all().order_by("number")]
    context = {
        **_base_context(),
        "tables": tables,
    }
    return render(request, "orders/tables_overview.html", context)


@require_GET
@login_required
def order_detail(request: HttpRequest, pk: int):
    order = get_object_or_404(
        Order.objects.select_related("waiter", "table").prefetch_related("items__product"),
        pk=pk,
    )
    return render(request, "orders/order_detail.html", {"order": order, **_base_context()})


@require_GET
@login_required
def table_bill(request: HttpRequest, table_id: int):
    table = get_object_or_404(DiningTable, pk=table_id)
    summary = _table_summary(table)
    return render(request, "orders/table_bill.html", {**summary, **_base_context()})


@require_GET
@login_required
def table_print(request: HttpRequest, table_id: int):
    table = get_object_or_404(DiningTable, pk=table_id)
    summary = _table_summary(table)
    summary["auto_print"] = True
    return render(request, "orders/table_print.html", summary)


@require_GET
@login_required
def kitchen_print(request: HttpRequest, pk: int):
    """Oshxona uchun qisqa chek (narxlarsiz)."""
    order = get_object_or_404(
        Order.objects.select_related("waiter", "table").prefetch_related("items__product"),
        pk=pk,
    )
    return render(request, "orders/kitchen_print.html", {"order": order, "auto_print": True})


@require_POST
@login_required
def close_table(request: HttpRequest, table_id: int):
    table = get_object_or_404(DiningTable, pk=table_id)
    bill_number = request.POST.get("bill_number")
    
    orders = Order.objects.filter(table=table, status__in=ACTIVE_ORDER_STATUSES)
    if bill_number:
        orders = orders.filter(bill_number=bill_number)
    
    orders = orders.prefetch_related("items")
    
    with transaction.atomic():
        for order in orders:
            order.items.filter(status=OrderItem.Status.PENDING).update(status=OrderItem.Status.ACCEPTED)
            order.status = Order.Status.COMPLETED
            order.save(update_fields=["status", "updated_at"])
            
    # Agar barcha shotlar yopilgan bo'lsa, ofitsantlarni bo'shatamiz
    if not Order.objects.filter(table=table, status__in=ACTIVE_ORDER_STATUSES).exists():
        table.assigned_waiters.clear()
        
    return redirect("orders:table_bill", table_id=table_id)


@require_POST
@login_required
def accept_order(request: HttpRequest, pk: int):
    order = get_object_or_404(Order.objects.select_related("table", "waiter__user").prefetch_related("items"), pk=pk)
    order.items.filter(status=OrderItem.Status.PENDING).update(status=OrderItem.Status.ACCEPTED)
    if order.items.filter(status=OrderItem.Status.REJECTED).exists():
        order.status = Order.Status.PARTIALLY_REJECTED
    else:
        order.status = Order.Status.ACCEPTED
    order.save(update_fields=["status", "updated_at"])
    _attach_order_to_table(order)
    return redirect("orders:order_detail", pk=pk)


@require_POST
@login_required
def reject_item(request: HttpRequest, pk: int, item_id: int):
    order = get_object_or_404(Order, pk=pk)
    item = get_object_or_404(OrderItem, pk=item_id, order=order)
    reason = request.POST.get("reason", "").strip() or "Kassada rad etildi"
    item.status = OrderItem.Status.REJECTED
    item.rejection_reason = reason
    item.save(update_fields=["status", "rejection_reason"])
    order.status = Order.Status.PARTIALLY_REJECTED
    order.save(update_fields=["status", "updated_at"])
    return redirect("orders:order_detail", pk=pk)
