import base64
import io
import json
from decimal import Decimal, InvalidOperation
from functools import wraps

import qrcode

from django.contrib.auth import authenticate
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.views.decorators.http import require_GET, require_POST

from .models import (
    DiningTable,
    MenuCategory,
    Order,
    OrderItem,
    Payment,
    Product,
    ProductDailyStock,
    Shift,
    UserProfile,
    Waiter,
)
from .services import ACTIVE_ORDER_STATUSES, table_summary


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
        "shift_open": Shift.is_open(),
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
    tables = [table_summary(table) for table in DiningTable.objects.all().order_by("number")]
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
    return render(request, "orders/order_detail.html", {
        "order": order,
        "shift_open": Shift.is_open(),
        "norej": request.GET.get("norej") == "1",
        **_base_context(),
    })


@require_GET
@login_required
def table_bill(request: HttpRequest, table_id: int):
    table = get_object_or_404(DiningTable, pk=table_id)
    summary = table_summary(table)
    return render(request, "orders/table_bill.html", {**summary, **_base_context()})


@require_GET
@login_required
def table_print(request: HttpRequest, table_id: int):
    table = get_object_or_404(DiningTable, pk=table_id)
    summary = table_summary(table)
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


PAYMENT_LABELS = {
    Payment.Method.CASH: "Naqd",
    Payment.Method.CARD: "Karta",
}


@require_POST
@login_required
def close_table(request: HttpRequest, table_id: int):
    table = get_object_or_404(DiningTable, pk=table_id)
    bill_number = request.POST.get("bill_number")

    payment_method = request.POST.get("payment_method")
    if payment_method not in (Payment.Method.CASH, Payment.Method.CARD):
        payment_method = Payment.Method.CASH

    orders = Order.objects.filter(table=table, status__in=ACTIVE_ORDER_STATUSES)
    if bill_number:
        orders = orders.filter(bill_number=bill_number)

    orders = list(
        orders.select_related("waiter", "table").prefetch_related("items__product")
    )

    if not orders:
        return redirect("orders:table_bill", table_id=table_id)

    total_paid = Decimal("0")
    with transaction.atomic():
        for order in orders:
            order.items.filter(status=OrderItem.Status.PENDING).update(
                status=OrderItem.Status.ACCEPTED
            )
            amount = order.payable_amount
            if not hasattr(order, "payment"):
                Payment.objects.create(
                    order=order,
                    payment_method=payment_method,
                    amount=amount,
                    cashier=request.user,
                )
            total_paid += amount
            order.status = Order.Status.COMPLETED
            order.save(update_fields=["status", "updated_at"])

    # Agar barcha shotlar yopilgan bo'lsa, ofitsantlarni bo'shatamiz
    if not Order.objects.filter(table=table, status__in=ACTIVE_ORDER_STATUSES).exists():
        table.assigned_waiters.clear()

    # Yopilgan hisob uchun chek (to'lov turi bilan) — avtomatik chop etiladi.
    items_count = sum(order.items.count() for order in orders)
    return render(request, "orders/table_print.html", {
        "table": table,
        "active_orders": orders,
        "orders_count": len(orders),
        "items_count": items_count,
        "total_amount": total_paid,
        "payment_method": payment_method,
        "payment_label": PAYMENT_LABELS.get(payment_method, "Naqd"),
        "auto_print": True,
    })


@require_POST
@login_required
def accept_order(request: HttpRequest, pk: int):
    if not Shift.is_open():
        return redirect("/smena/?need_shift=1")
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
    item = get_object_or_404(OrderItem.objects.select_related("product"), pk=item_id, order=order)
    if not item.product.is_rejectable:
        # Bu taom rad etib bo'lmaydigan deb belgilangan.
        return redirect(f"/orders/{pk}/?norej=1")
    reason = request.POST.get("reason", "").strip() or "Kassada rad etildi"
    item.status = OrderItem.Status.REJECTED
    item.rejection_reason = reason
    item.save(update_fields=["status", "rejection_reason"])
    order.status = Order.Status.PARTIALLY_REJECTED
    order.save(update_fields=["status", "updated_at"])
    return redirect("orders:order_detail", pk=pk)


@require_GET
@login_required
def waiters_list(request: HttpRequest):
    """Ofitsantlar ro'yxati (Kassir va Direktor uchun)."""
    # Bu view hozircha faqat ro'yxatni ko'rsatadi. 
    # To'liq CRUD (qoshish/o'chirish) API orqali yoki keyingi qadamda qo'shiladi.
    waiters = UserProfile.objects.filter(role=UserProfile.Role.WAITER).select_related('user')
    return render(request, "orders/waiters_list.html", {
        "waiters": waiters,
        "waiters_count": waiters.count(),
        **_base_context()
    })


@require_POST
@login_required
def create_waiter(request: HttpRequest):
    """Yangi ofitsant qo'shish (Web orqali)."""
    # Faqat Direktor yoki Kassir qo'sha oladi
    profile = getattr(request.user, "profile", None)
    if not profile or profile.role not in ['director', 'cashier']:
        return HttpResponseBadRequest("Ruxsat berilmagan")

    username = request.POST.get("username")
    password = request.POST.get("password")
    full_name = request.POST.get("full_name")
    
    if not all([username, password, full_name]):
        return HttpResponseBadRequest("Barcha maydonlarni to'ldiring")

    from django.contrib.auth.models import User
    from django.contrib.auth.hashers import make_password
    
    if User.objects.filter(username=username).exists():
        return HttpResponseBadRequest("Bunday login band")

    with transaction.atomic():
        user = User.objects.create(
            username=username,
            password=make_password(password),
            is_active=True
        )
        UserProfile.objects.create(
            user=user,
            full_name=full_name,
            role=UserProfile.Role.WAITER
        )
        # Shuningdek legacy Waiter modeliga ham qo'shamiz (agar kerak bo'lsa)
        Waiter.objects.create(
            user=user,
            full_name=full_name
        )

    return redirect("orders:waiters_list")


@require_POST
@login_required
def delete_waiter(request: HttpRequest, user_id: int):
    """Ofitsantni o'chirish (Web orqali). Faqat Direktor yoki Kassir."""
    profile = getattr(request.user, "profile", None)
    if not (request.user.is_superuser or (profile and profile.role in ['director', 'cashier'])):
        return HttpResponseBadRequest("Ruxsat berilmagan")

    from django.contrib.auth.models import User

    waiter_user = get_object_or_404(
        User, pk=user_id, profile__role=UserProfile.Role.WAITER
    )

    with transaction.atomic():
        # Legacy Waiter yozuvini ham olib tashlaymiz (user SET_NULL bo'lgani uchun
        # User o'chsa null bo'lib qoladi — shuning uchun avval o'chiramiz).
        Waiter.objects.filter(user=waiter_user).delete()
        # User o'chirilsa UserProfile (CASCADE) ham o'chadi.
        waiter_user.delete()

    return redirect("orders:waiters_list")


# ============================================================
# MENYU BOSHQARUVI (Kassir / Direktor) — to'liq CRUD
# ============================================================

def _is_manager(request: HttpRequest) -> bool:
    """Kassir, direktor yoki superuser menyu/sig'imni boshqara oladi."""
    if request.user.is_superuser:
        return True
    profile = getattr(request.user, "profile", None)
    return bool(profile and profile.role in ("director", "cashier"))


def _parse_price(raw):
    try:
        value = Decimal(str(raw).replace(" ", "").replace(",", "."))
    except (InvalidOperation, AttributeError, TypeError):
        return None
    if value < 0:
        return None
    return value


@require_GET
@login_required
def menu_list(request: HttpRequest):
    """Menyu boshqaruvi: mahsulot va kategoriyalar ro'yxati."""
    products = (
        Product.objects.select_related("category").order_by("category__sort_order", "name")
    )
    categories = MenuCategory.objects.all()
    return render(request, "orders/menu_list.html", {
        "products": products,
        "categories": categories,
        "products_count": products.count(),
        **_base_context(),
    })


@require_POST
@login_required
def menu_create(request: HttpRequest):
    if not _is_manager(request):
        return HttpResponseBadRequest("Ruxsat berilmagan")

    name = (request.POST.get("name") or "").strip()
    price = _parse_price(request.POST.get("price"))
    if not name or price is None:
        return HttpResponseBadRequest("Nom va to'g'ri narx kiriting")

    category_id = request.POST.get("category") or None
    category = MenuCategory.objects.filter(pk=category_id).first() if category_id else None

    Product.objects.create(
        name=name,
        category=category,
        price=price,
        description=(request.POST.get("description") or "").strip(),
        is_active=request.POST.get("is_active") == "on",
        is_rejectable=request.POST.get("is_rejectable") == "on",
    )
    return redirect("orders:menu_list")


@require_POST
@login_required
def menu_update(request: HttpRequest, pk: int):
    if not _is_manager(request):
        return HttpResponseBadRequest("Ruxsat berilmagan")

    product = get_object_or_404(Product, pk=pk)
    name = (request.POST.get("name") or "").strip()
    price = _parse_price(request.POST.get("price"))
    if not name or price is None:
        return HttpResponseBadRequest("Nom va to'g'ri narx kiriting")

    category_id = request.POST.get("category") or None
    product.name = name
    product.price = price
    product.category = MenuCategory.objects.filter(pk=category_id).first() if category_id else None
    product.description = (request.POST.get("description") or "").strip()
    product.is_active = request.POST.get("is_active") == "on"
    product.is_rejectable = request.POST.get("is_rejectable") == "on"
    product.save()
    return redirect("orders:menu_list")


@require_POST
@login_required
def menu_delete(request: HttpRequest, pk: int):
    if not _is_manager(request):
        return HttpResponseBadRequest("Ruxsat berilmagan")
    get_object_or_404(Product, pk=pk).delete()
    return redirect("orders:menu_list")


@require_POST
@login_required
def category_create(request: HttpRequest):
    if not _is_manager(request):
        return HttpResponseBadRequest("Ruxsat berilmagan")
    name = (request.POST.get("name") or "").strip()
    if not name:
        return HttpResponseBadRequest("Kategoriya nomi kiriting")
    sort_order = request.POST.get("sort_order") or 0
    try:
        sort_order = int(sort_order)
    except (TypeError, ValueError):
        sort_order = 0
    MenuCategory.objects.get_or_create(name=name, defaults={"sort_order": sort_order})
    return redirect("orders:menu_list")


# ============================================================
# SMENA BOSHLASH — kunlik portsiya jadvali
# ============================================================

@require_GET
@login_required
def daily_stock(request: HttpRequest):
    """Bugungi smena uchun har bir mahsulotning portsiya soni."""
    today = timezone.localdate()
    products = (
        Product.objects.filter(is_active=True)
        .select_related("category")
        .order_by("category__sort_order", "name")
    )
    stock_map = {
        s.product_id: s
        for s in ProductDailyStock.objects.filter(date=today)
    }
    groups = {}
    for product in products:
        stock = stock_map.get(product.id)
        key = product.category_id or 0
        bucket = groups.setdefault(key, {
            "id": key,
            "name": product.category.name if product.category else "Kategoriyasiz",
            "rows": [],
        })
        bucket["rows"].append({
            "product": product,
            "is_set": stock is not None,
            "initial": stock.initial_quantity if stock else "",
            "remaining": stock.remaining_quantity if stock else None,
        })
    shift = Shift.objects.filter(date=today).first()
    return render(request, "orders/daily_stock.html", {
        "groups": list(groups.values()),
        "today": today,
        "set_count": len(stock_map),
        "products_count": products.count(),
        "shift_open": shift is not None,
        "shift": shift,
        "need_shift": request.GET.get("need_shift") == "1",
        **_base_context(),
    })


@require_POST
@login_required
def daily_stock_save(request: HttpRequest):
    """Smenani boshlash: bugungi portsiyalarni saqlash.

    Allaqachon iste'mol qilingan miqdor saqlanadi — boshlang'ich
    o'zgartirilsa, qolgan = yangi_boshlang'ich − iste'mol.
    """
    if not _is_manager(request):
        return HttpResponseBadRequest("Ruxsat berilmagan")
    if not Shift.is_open():
        # Smena ochilmagan — portsiya kiritib bo'lmaydi.
        return redirect("/smena/?need_shift=1")

    today = timezone.localdate()
    product_ids = list(
        Product.objects.filter(is_active=True).values_list("id", flat=True)
    )
    existing = {
        s.product_id: s
        for s in ProductDailyStock.objects.filter(date=today)
    }

    with transaction.atomic():
        for product_id in product_ids:
            raw = request.POST.get(f"qty_{product_id}", "").strip()
            stock = existing.get(product_id)

            if raw == "":
                # Bo'sh qoldirilsa — cheksiz (sig'im belgilanmagan): mavjud yozuvni o'chiramiz.
                if stock:
                    stock.delete()
                continue

            try:
                qty = int(raw)
            except ValueError:
                continue
            if qty < 0:
                qty = 0

            if stock:
                consumed = max(stock.initial_quantity - stock.remaining_quantity, 0)
                stock.initial_quantity = qty
                stock.remaining_quantity = max(qty - consumed, 0)
                stock.set_by = request.user
                stock.save(update_fields=[
                    "initial_quantity", "remaining_quantity", "set_by", "updated_at",
                ])
            else:
                ProductDailyStock.objects.create(
                    product_id=product_id,
                    date=today,
                    initial_quantity=qty,
                    remaining_quantity=qty,
                    set_by=request.user,
                )

    return redirect("orders:daily_stock")


@require_POST
@login_required
def start_shift(request: HttpRequest):
    """Bugungi smenani ochish. Shundan keyingina buyurtma qabul
    qilinadi va portsiya kiritiladi."""
    if not _is_manager(request):
        return HttpResponseBadRequest("Ruxsat berilmagan")
    Shift.objects.get_or_create(
        date=timezone.localdate(),
        defaults={"opened_by": request.user},
    )
    return redirect("orders:daily_stock")


@require_GET
@login_required
def tables_qr(request: HttpRequest):
    """Har bir stol uchun QR kod (chop etish / yuklab olish)."""
    if not _is_manager(request):
        return HttpResponseBadRequest("Ruxsat berilmagan")
    base = request.build_absolute_uri("/").rstrip("/")
    cards = []
    for table in DiningTable.objects.order_by("number"):
        url = f"{base}/m/{table.qr_token}/"
        img = qrcode.make(url, box_size=9, border=2)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        cards.append({
            "table": table,
            "url": url,
            "data": base64.b64encode(buf.getvalue()).decode(),
        })
    return render(request, "orders/tables_qr.html", {
        "cards": cards,
        "tables_count": len(cards),
        **_base_context(),
    })


# ============================================================
# MIJOZ — QR orqali o'z-o'ziga xizmat (public, auth kerak emas)
# ============================================================

def _client_menu_groups(request):
    """QR menyu uchun kategoriya/mahsulotlar (sig'im bilan)."""
    today = timezone.localdate()
    products = Product.objects.filter(is_active=True).select_related("category")
    stocks = {s.product_id: s for s in ProductDailyStock.objects.filter(date=today)}
    groups = {}
    for p in products:
        stock = stocks.get(p.id)
        remaining = stock.remaining_quantity if stock else None
        key = p.category_id or 0
        bucket = groups.setdefault(key, {
            "id": key,
            "name": p.category.name if p.category else "Boshqa",
            "items": [],
        })
        bucket["items"].append({
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "price": p.price,
            "is_rejectable": p.is_rejectable,
            "remaining": remaining,
            "is_available": not (remaining is not None and remaining <= 0),
            "image_url": request.build_absolute_uri(p.image.url) if p.image else None,
        })
    return list(groups.values())


@require_GET
def client_menu(request: HttpRequest, qr_token: str):
    table = get_object_or_404(DiningTable, qr_token=qr_token)
    return render(request, "client/menu.html", {
        "table": table,
        "qr_token": qr_token,
        "groups": _client_menu_groups(request),
        "error": request.GET.get("error"),
    })


@require_POST
def client_order_create(request: HttpRequest, qr_token: str):
    table = get_object_or_404(DiningTable, qr_token=qr_token)
    client_name = (request.POST.get("client_name") or "").strip()
    note = (request.POST.get("note") or "").strip()

    try:
        cart = json.loads(request.POST.get("items") or "[]")
    except (json.JSONDecodeError, TypeError):
        cart = []

    cart = [
        c for c in cart
        if isinstance(c, dict) and int(c.get("quantity", 0)) > 0
    ]

    if not client_name:
        return redirect(f"/m/{qr_token}/?error=Ismingizni kiriting")
    if not cart:
        return redirect(f"/m/{qr_token}/?error=Savat bo'sh")

    today = timezone.localdate()
    try:
        with transaction.atomic():
            order = Order.objects.create(
                external_id=f"CLIENT-{table.number}-{get_random_string(16)}",
                waiter=None,
                table=table,
                bill_number=1,
                note=note,
                status=Order.Status.NEW,
                order_source=Order.OrderSource.CLIENT,
                client_name=client_name,
            )
            for c in cart:
                quantity = int(c["quantity"])
                product = get_object_or_404(
                    Product, pk=int(c["menu_item_id"]), is_active=True
                )
                remaining = product.get_today_remaining()
                if remaining is not None and remaining < quantity:
                    raise ValueError(
                        f"{product.name}: yetarli emas (qolgan {remaining})"
                    )
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=quantity,
                    note=(c.get("note") or "").strip(),
                )
                stock = ProductDailyStock.objects.filter(
                    product=product, date=today
                ).first()
                if stock:
                    stock.remaining_quantity = max(
                        0, stock.remaining_quantity - quantity
                    )
                    stock.save(update_fields=["remaining_quantity", "updated_at"])
    except ValueError as exc:
        return redirect(f"/m/{qr_token}/?error={exc}")

    return redirect(f"/m/order/{order.id}/?t={order.public_token}")


@require_GET
def client_order_status(request: HttpRequest, order_id: int):
    token = request.GET.get("t")
    order = get_object_or_404(
        Order.objects.select_related("table").prefetch_related("items__product"),
        pk=order_id,
        order_source=Order.OrderSource.CLIENT,
        public_token=token,
    )
    return render(request, "client/status.html", {
        "order": order,
        "token": token,
        "can_edit": order.status in (Order.Status.NEW, Order.Status.ACCEPTED),
    })


@require_POST
def client_reject_item(request: HttpRequest, order_id: int, item_id: int):
    token = request.POST.get("t") or request.GET.get("t")
    order = get_object_or_404(
        Order.objects.prefetch_related("items__product"),
        pk=order_id,
        order_source=Order.OrderSource.CLIENT,
        public_token=token,
    )
    redirect_url = f"/m/order/{order_id}/?t={token}"

    if order.status not in (Order.Status.NEW, Order.Status.ACCEPTED):
        return redirect(redirect_url)

    item = get_object_or_404(
        OrderItem.objects.select_related("product"), pk=item_id, order=order
    )
    if not item.product.is_rejectable or item.status == OrderItem.Status.REJECTED:
        return redirect(redirect_url)

    with transaction.atomic():
        item.status = OrderItem.Status.REJECTED
        item.rejection_reason = "Mijoz tomonidan rad etildi"
        item.save(update_fields=["status", "rejection_reason"])

        stock = ProductDailyStock.objects.filter(
            product=item.product, date=timezone.localdate()
        ).first()
        if stock:
            stock.remaining_quantity += item.quantity
            stock.save(update_fields=["remaining_quantity", "updated_at"])

        if order.items.exclude(status=OrderItem.Status.REJECTED).count() == 0:
            order.status = Order.Status.CANCELLED
        else:
            order.status = Order.Status.PARTIALLY_REJECTED
        order.save(update_fields=["status", "updated_at"])

    return redirect(redirect_url)
