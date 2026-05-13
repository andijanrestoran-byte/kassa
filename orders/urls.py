from django.urls import path

from rest_framework_simplejwt.views import TokenRefreshView

from . import api_views, api_views_new, views

app_name = "orders"

urlpatterns = [
    # ── Web sahifalar ──
    path("", views.dashboard, name="dashboard"),
    path("orders/", views.orders_list, name="orders_list"),
    path("rejected/", views.rejected_orders, name="rejected_orders"),
    path("tables/", views.tables_overview, name="tables_overview"),
    path("orders/<int:pk>/", views.order_detail, name="order_detail"),
    path("orders/<int:pk>/accept/", views.accept_order, name="accept_order"),
    path("orders/<int:pk>/items/<int:item_id>/reject/", views.reject_item, name="reject_item"),
    path("tables/<int:table_id>/", views.table_bill, name="table_bill"),
    path("tables/<int:table_id>/print/", views.table_print, name="table_print"),
    path("orders/<int:pk>/kitchen-print/", views.kitchen_print, name="kitchen_print"),
    path("waiters/", views.waiters_list, name="waiters_list"),
    path("waiters/create/", views.create_waiter, name="create_waiter"),
    path("tables/<int:table_id>/close/", views.close_table, name="close_table"),

    # ── API v1 — Auth ──
    path("api/v1/auth/login", api_views.LoginView.as_view(), name="v1_login"),
    path("api/v1/auth/refresh", TokenRefreshView.as_view(), name="v1_refresh"),
    path("api/v1/auth/me", api_views.MeView.as_view(), name="v1_me"),

    # ── API v1 — Stollar ──
    path("api/v1/tables", api_views.TablesListView.as_view(), name="v1_tables"),
    path("api/v1/tables/<int:table_id>/join", api_views.TableJoinView.as_view(), name="v1_table_join"),

    # ── API v1 — Menyu ──
    path("api/v1/menu/categories", api_views.MenuCategoryListCreateView.as_view(), name="v1_menu_categories"),
    path("api/v1/menu/categories/<int:pk>", api_views.MenuCategoryDetailView.as_view(), name="v1_menu_category_detail"),
    path("api/v1/menu/items", api_views.MenuItemsListCreateView.as_view(), name="v1_menu_items"),
    path("api/v1/menu/items/<int:pk>", api_views.MenuItemDetailView.as_view(), name="v1_menu_item_detail"),

    # ── API v1 — Buyurtmalar ──
    path("api/v1/orders", api_views.OrdersListCreateView.as_view(), name="v1_orders"),
    path("api/v1/orders/<int:order_id>", api_views.OrderDetailView.as_view(), name="v1_order_detail"),
    path("api/v1/orders/<int:order_id>/reject", api_views.RejectOrderView.as_view(), name="v1_order_reject"),
    path("api/v1/orders/<int:order_id>/cancel", api_views.CancelOrderView.as_view(), name="v1_order_cancel"),

    # ── API v1 — To'lovlar ──
    path("api/v1/payments", api_views.PaymentsView.as_view(), name="v1_payments"),

    # ── API v1 — Dashboard ──
    path("api/v1/dashboard/summary", api_views.DashboardSummaryView.as_view(), name="v1_dashboard_summary"),
    path("api/v1/waiters/overview", api_views.WaitersOverviewView.as_view(), name="v1_waiters_overview"),

    # ── YANGI: Direktor — Ofitsant CRUD ──
    path("api/v1/director/waiters", api_views_new.DirectorWaitersView.as_view(), name="v1_director_waiters"),
    path("api/v1/director/waiters/<int:user_id>", api_views_new.DirectorWaiterDetailView.as_view(), name="v1_director_waiter_detail"),

    # ── YANGI: Direktor — Hisobotlar ──
    path("api/v1/director/reports/revenue", api_views_new.RevenueReportView.as_view(), name="v1_director_revenue"),
    path("api/v1/director/reports/waiters", api_views_new.WaiterReportView.as_view(), name="v1_director_waiter_report"),
    path("api/v1/director/reports/waiters/<int:user_id>", api_views_new.WaiterDetailReportView.as_view(), name="v1_director_waiter_detail_report"),

    # ── YANGI: Direktor — QR kod ──
    path("api/v1/director/tables/<int:table_id>/qr", api_views_new.TableQRCodeView.as_view(), name="v1_table_qr"),

    # ── YANGI: Kassir — Sig'im va buyurtma qabul ──
    path("api/v1/cashier/daily-stock", api_views_new.DailyStockView.as_view(), name="v1_daily_stock"),
    path("api/v1/cashier/orders/pending", api_views_new.CashierPendingOrdersView.as_view(), name="v1_cashier_pending"),
    path("api/v1/cashier/orders/<int:order_id>/accept", api_views_new.CashierAcceptOrderView.as_view(), name="v1_cashier_accept"),
    path("api/v1/cashier/tables/<int:table_id>/bill", api_views_new.CashierTableBillView.as_view(), name="v1_cashier_table_bill"),
    path("api/v1/cashier/tables/<int:table_id>/close", api_views_new.CashierCloseTableView.as_view(), name="v1_cashier_close_table"),

    # ── YANGI: Mijoz — QR menyu va o'z-o'ziga xizmat (public, auth kerak emas) ──
    path("api/v1/public/menu/<str:qr_token>", api_views_new.PublicMenuView.as_view(), name="v1_public_menu"),
    path("api/v1/public/orders/<str:qr_token>", api_views_new.PublicClientOrderView.as_view(), name="v1_public_order"),
    path("api/v1/public/order-status/<int:order_id>", api_views_new.PublicOrderStatusView.as_view(), name="v1_public_order_status"),
    path("api/v1/public/orders/<int:order_id>/items/<int:item_id>/reject", api_views_new.PublicClientRejectItemView.as_view(), name="v1_public_reject_item"),

    # ── YANGI: Ofitsant — Barcha stollar ──
    path("api/v1/waiter/all-tables", api_views_new.WaiterAllTablesView.as_view(), name="v1_waiter_all_tables"),

    # ── Mobil platform aliaslar ──
    path("api/auth/login/", api_views.LoginView.as_view(), name="api_login"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="api_refresh"),
    path("api/auth/me/", api_views.MeView.as_view(), name="api_me"),
    path("api/staff/menu/items/", api_views.MenuItemsListCreateView.as_view(), name="api_staff_menu_items"),
    path("api/staff/menu/items/<int:pk>/", api_views.MenuItemDetailView.as_view(), name="api_staff_menu_item_detail"),
    path("api/staff/menu/categories/", api_views.MenuCategoryListCreateView.as_view(), name="api_staff_menu_categories"),
    path("api/staff/menu/categories/<int:pk>/", api_views.MenuCategoryDetailView.as_view(), name="api_staff_menu_category_detail"),
    path("api/staff/orders/", api_views.OrdersListCreateView.as_view(), name="api_staff_orders"),
    path("api/staff/orders/<int:order_id>/reject/", api_views.RejectOrderView.as_view(), name="api_staff_order_reject"),
    path("api/staff/orders/<int:order_id>/cancel/", api_views.CancelOrderView.as_view(), name="api_staff_order_cancel"),
    path("api/cashier/payments/", api_views.PaymentsView.as_view(), name="api_cashier_payments"),
    path("api/cashier/payments/<int:payment_id>/", api_views.PaymentDetailView.as_view(), name="api_cashier_payment_detail"),
    path("api/dashboard/summary/", api_views.DashboardSummaryView.as_view(), name="api_dashboard_summary"),
    path("api/staff/tables/", api_views.StaffTablesView.as_view(), name="api_staff_tables"),
]
