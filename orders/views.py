import json
from decimal import Decimal
from functools import wraps

from django.contrib.auth import authenticate
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from .models import ApiToken, DiningTable, MenuCategory, Order, OrderItem, Product, UserProfile, Waiter

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
        .order_by("-created_at")
    )
    total_amount = sum((_order_total(order) for order in active_orders), Decimal("0"))
    total_items = sum(order.items.count() for order in active_orders)
    latest_order = active_orders[0] if active_orders else None
    return {
        "table": table,
        "active_orders": active_orders,
        "orders_count": len(active_orders),
        "items_count": total_items,
        "total_amount": total_amount,
        "latest_order": latest_order,
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


def _table_has_open_bill(table: DiningTable) -> bool:
    return Order.objects.filter(table=table, status__in=ACTIVE_ORDER_STATUSES).exists()


def _serialize_order_item(item: OrderItem):
    return {
        "id": item.id,
        "product_id": item.product_id,
        "product_name": item.product.name,
        "quantity": item.quantity,
        "price": str(item.product.price),
        "line_total": str(item.line_total),
        "status": item.status,
        "status_label": item.get_status_display(),
        "rejection_reason": item.rejection_reason,
    }


def _serialize_order(order: Order, include_items: bool = True):
    payload = {
        "id": order.id,
        "external_id": order.external_id,
        "status": order.status,
        "status_label": order.get_status_display(),
        "waiter": {
            "id": order.waiter_id,
            "full_name": order.waiter.full_name if order.waiter else "Mijoz",
            "phone": order.waiter.phone if order.waiter else "",
        },
        "table": {
            "id": order.table_id,
            "number": order.table.number,
            "zone": order.table.zone,
        },
        "note": order.note,
        "total_amount": str(order.total_amount),
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
    }
    if include_items:
        payload["items"] = [_serialize_order_item(item) for item in order.items.all()]
    return payload


def _serialize_table_summary(summary):
    table = summary["table"]
    latest = summary["latest_order"]
    return {
        "id": table.id,
        "number": table.number,
        "zone": table.zone,
        "orders_count": summary["orders_count"],
        "items_count": summary["items_count"],
        "total_amount": str(summary["total_amount"]),
        "latest_order": {
            "id": latest.id,
            "external_id": latest.external_id,
            "status": latest.status,
            "source": latest.client_name if latest.order_source == Order.OrderSource.CLIENT else (latest.waiter.full_name if latest.waiter else "—")
        } if latest else None,
    }


def _serialize_menu_category(category: MenuCategory):
    return {
        "id": category.id,
        "name": category.name,
        "sort_order": category.sort_order,
    }


def _serialize_menu_item(product: Product):
    return {
        "id": product.id,
        "name": product.name,
        "category_id": product.category_id,
        "category_name": product.category.name if product.category else None,
        "description": product.description,
        "price": str(product.price),
        "is_active": product.is_active,
    }


def _json_error(message: str, status: int = 400):
    return JsonResponse({"error": message}, status=status)


def _parse_json_body(request: HttpRequest):
    try:
        return json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def api_token_required(view_func):
    @wraps(view_func)
    def wrapper(request: HttpRequest, *args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return _json_error("Authorization Bearer token yuborilishi kerak.", status=401)

        token_key = auth_header.removeprefix("Bearer ").strip()
        token = (
            ApiToken.objects.select_related("user")
            .filter(key=token_key)
            .first()
        )
        if token is None:
            return _json_error("Token yaroqsiz yoki eskirgan.", status=401)

        request.api_user = token.user
        request.api_token = token
        return view_func(request, *args, **kwargs)

    return wrapper


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


@require_POST
@login_required
def close_table(request: HttpRequest, table_id: int):
    table = get_object_or_404(DiningTable, pk=table_id)
    orders = Order.objects.filter(table=table, status__in=ACTIVE_ORDER_STATUSES).prefetch_related("items")
    for order in orders:
        order.items.filter(status=OrderItem.Status.PENDING).update(status=OrderItem.Status.ACCEPTED)
        order.status = Order.Status.COMPLETED
        order.save(update_fields=["status", "updated_at"])
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


@require_POST
def api_login(request: HttpRequest):
    payload = _parse_json_body(request)
    if payload is None:
        return _json_error("Yaroqsiz JSON yuborildi.")

    username = payload.get("username", "").strip()
    password = payload.get("password", "")
    if not username or not password:
        return _json_error("username va password majburiy.")

    user = authenticate(request, username=username, password=password)
    if user is None:
        return _json_error("Login yoki parol noto'g'ri.", status=401)

    token = ApiToken.objects.create(user=user, key=ApiToken.generate_key())
    return JsonResponse(
        {
            "token": token.key,
            "user": {
                "id": user.id,
                "username": user.username,
            },
        }
    )


@require_POST
@api_token_required
def api_logout(request: HttpRequest):
    request.api_token.delete()
    return JsonResponse({"success": True})


@require_GET
@api_token_required
def api_me(request: HttpRequest):
    user = request.api_user
    profile = getattr(user, "profile", None)
    return JsonResponse(
        {
            "user": {
                "id": user.id,
                "username": user.username,
                "full_name": profile.full_name if profile else user.username,
                "role": profile.role if profile else UserProfile.Role.WAITER,
            }
        }
    )


@require_GET
@api_token_required
def api_orders(request: HttpRequest):
    status_filter = request.GET.get("status", "").strip()
    orders = (
        Order.objects.select_related("waiter", "table")
        .prefetch_related("items__product")
        .order_by("-created_at")
    )
    if status_filter:
        orders = orders.filter(status=status_filter)
    else:
        orders = orders.filter(status__in=ACTIVE_ORDER_STATUSES)

    return JsonResponse({"results": [_serialize_order(order) for order in orders]})


@require_GET
@api_token_required
def api_order_detail(request: HttpRequest, pk: int):
    order = get_object_or_404(
        Order.objects.select_related("waiter", "table").prefetch_related("items__product"),
        pk=pk,
    )
    return JsonResponse(_serialize_order(order))


@require_POST
@api_token_required
def api_accept_order(request: HttpRequest, pk: int):
    order = get_object_or_404(Order.objects.prefetch_related("items"), pk=pk)
    order.items.filter(status=OrderItem.Status.PENDING).update(status=OrderItem.Status.ACCEPTED)
    if order.items.filter(status=OrderItem.Status.REJECTED).exists():
        order.status = Order.Status.PARTIALLY_REJECTED
    else:
        order.status = Order.Status.ACCEPTED
    order.save(update_fields=["status", "updated_at"])
    order.refresh_from_db()
    return JsonResponse(_serialize_order(order))


@require_POST
@api_token_required
def api_reject_order_item(request: HttpRequest, pk: int, item_id: int):
    payload = _parse_json_body(request) or {}
    reason = payload.get("reason", "").strip() or "Kassada rad etildi"

    order = get_object_or_404(Order, pk=pk)
    item = get_object_or_404(OrderItem, pk=item_id, order=order)
    item.status = OrderItem.Status.REJECTED
    item.rejection_reason = reason
    item.save(update_fields=["status", "rejection_reason"])
    order.status = Order.Status.PARTIALLY_REJECTED
    order.save(update_fields=["status", "updated_at"])
    order = Order.objects.select_related("waiter", "table").prefetch_related("items__product").get(pk=order.pk)
    return JsonResponse(_serialize_order(order))


@require_GET
@api_token_required
def api_rejected_orders(request: HttpRequest):
    orders = (
        Order.objects.filter(status=Order.Status.PARTIALLY_REJECTED)
        .select_related("waiter", "table")
        .prefetch_related("items__product")
        .order_by("-updated_at")
    )
    return JsonResponse({"results": [_serialize_order(order) for order in orders]})


@require_GET
@api_token_required
def api_menu_categories(request: HttpRequest):
    categories = MenuCategory.objects.all().order_by("sort_order", "name")
    return JsonResponse({"results": [_serialize_menu_category(category) for category in categories]})


@require_GET
@api_token_required
def api_menu_items(request: HttpRequest):
    items = Product.objects.select_related("category").filter(is_active=True).order_by("name")
    category_id = request.GET.get("category_id", "").strip()
    if category_id:
        items = items.filter(category_id=category_id)
    return JsonResponse({"results": [_serialize_menu_item(item) for item in items]})


@require_GET
@api_token_required
def api_tables(request: HttpRequest):
    tables = [_table_summary(table) for table in DiningTable.objects.all().order_by("number")]
    return JsonResponse({"results": [_serialize_table_summary(entry) for entry in tables]})


@require_GET
@api_token_required
def api_table_detail(request: HttpRequest, table_id: int):
    table = get_object_or_404(DiningTable, pk=table_id)
    summary = _table_summary(table)
    payload = _serialize_table_summary(summary)
    payload["orders"] = [_serialize_order(order) for order in summary["active_orders"]]
    return JsonResponse(payload)


@require_POST
def create_mobile_order(request: HttpRequest):
    payload = _parse_json_body(request)
    if payload is None:
        return HttpResponseBadRequest("Yaroqsiz JSON yuborildi.")

    required_keys = {"external_id", "waiter", "table", "items"}
    if not required_keys.issubset(payload):
        return HttpResponseBadRequest("external_id, waiter, table va items majburiy.")
    if not payload["items"]:
        return HttpResponseBadRequest("Kamida bitta mahsulot yuborilishi kerak.")

    with transaction.atomic():
        waiter, _ = Waiter.objects.get_or_create(full_name=payload["waiter"])
        table, _ = DiningTable.objects.get_or_create(number=payload["table"])
        auto_accept = _table_has_open_bill(table)
        order = Order.objects.create(
            external_id=payload["external_id"],
            waiter=waiter,
            table=table,
            note=payload.get("note", ""),
            status=Order.Status.ACCEPTED if auto_accept else Order.Status.NEW,
        )
        for item_data in payload["items"]:
            product, _ = Product.objects.get_or_create(
                name=item_data["name"],
                defaults={"price": item_data.get("price", 0)},
            )
            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=item_data.get("quantity", 1),
                status=OrderItem.Status.ACCEPTED if auto_accept else OrderItem.Status.PENDING,
            )

    return JsonResponse(
        {
            "id": order.id,
            "external_id": order.external_id,
            "status": order.status,
            "waiter": order.waiter.full_name,
            "table": order.table.number,
        },
        status=201,
    )
