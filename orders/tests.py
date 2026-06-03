import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.test import Client, TestCase
from django.urls import reverse

from .models import DiningTable, MenuCategory, Order, OrderItem, Payment, Product, ProductDailyStock, Shift, UserProfile, Waiter


class OrderFlowTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.csrf_client = Client(enforce_csrf_checks=True)
        self.user = get_user_model().objects.create_user(
            username="kassir_test",
            password="TestPass123!",
        )
        self.cashier_profile = UserProfile.objects.create(
            user=self.user,
            full_name="Kassir Test",
            role=UserProfile.Role.CASHIER,
            phone="+998900000001",
            shift="10:00 - 22:00",
            experience="2 yil",
        )
        self.waiter_user = get_user_model().objects.create_user(
            username="azizbek",
            password="12345",
        )
        self.waiter_profile = UserProfile.objects.create(
            user=self.waiter_user,
            full_name="Azizbek Karimov",
            role=UserProfile.Role.WAITER,
            phone="+998901234567",
            shift="10:00 - 22:00",
            experience="4 yil",
        )
        self.waiter = Waiter.objects.create(
            user=self.waiter_user,
            full_name=self.waiter_profile.full_name,
            phone=self.waiter_profile.phone,
            shift=self.waiter_profile.shift,
            experience=self.waiter_profile.experience,
        )
        self.director_user = get_user_model().objects.create_user(
            username="director_test",
            password="Director123!",
        )
        self.director_profile = UserProfile.objects.create(
            user=self.director_user,
            full_name="Director User",
            role=UserProfile.Role.DIRECTOR,
            phone="+998900000002",
            shift="09:00 - 18:00",
            experience="8 yil",
        )


    def test_session_login_form_accepts_trusted_origin(self):
        login_page = self.csrf_client.get(
            reverse("login"),
            HTTP_HOST="testserver",
            HTTP_ORIGIN="http://testserver",
        )
        self.assertEqual(login_page.status_code, 200)

        csrf_cookie = login_page.cookies["csrftoken"].value
        response = self.csrf_client.post(
            reverse("login"),
            data={"username": "kassir_test", "password": "TestPass123!", "csrfmiddlewaretoken": csrf_cookie},
            HTTP_HOST="testserver",
            HTTP_ORIGIN="http://testserver",
            HTTP_REFERER="http://testserver/accounts/login/",
        )

        self.assertEqual(response.status_code, 302)

    def test_cashier_can_logout_from_session(self):
        logged_in = self.client.login(username="kassir_test", password="TestPass123!")
        self.assertTrue(logged_in)

        response = self.client.post(reverse("logout"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("login"))
        self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(
        ALLOWED_HOSTS=["demo.up.railway.app"],
        CSRF_TRUSTED_ORIGINS=["https://demo.up.railway.app"],
        USE_X_FORWARDED_HOST=True,
        SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
    )
    def test_session_login_form_accepts_forwarded_https_origin(self):
        login_page = self.csrf_client.get(
            reverse("login"),
            HTTP_HOST="demo.up.railway.app",
            HTTP_X_FORWARDED_PROTO="https",
            HTTP_ORIGIN="https://demo.up.railway.app",
        )
        self.assertEqual(login_page.status_code, 200)

        csrf_cookie = login_page.cookies["csrftoken"].value
        response = self.csrf_client.post(
            reverse("login"),
            data={"username": "kassir_test", "password": "TestPass123!", "csrfmiddlewaretoken": csrf_cookie},
            HTTP_HOST="demo.up.railway.app",
            HTTP_X_FORWARDED_PROTO="https",
            HTTP_ORIGIN="https://demo.up.railway.app",
            HTTP_REFERER="https://demo.up.railway.app/accounts/login/",
        )

        self.assertEqual(response.status_code, 302)



    def test_reject_item_marks_order_as_partially_rejected(self):
        self.client.login(username="kassir_test", password="TestPass123!")
        waiter = Waiter.objects.create(full_name="Ali Valiyev")
        table = DiningTable.objects.create(number=103)
        product = Product.objects.create(name="Somsa", price=8000)
        order = Order.objects.create(external_id="MOB-1002", waiter=waiter, table=table)
        item = OrderItem.objects.create(order=order, product=product, quantity=1)

        response = self.client.post(
            reverse("orders:reject_item", args=[order.pk, item.pk]),
            {"reason": "Mahsulot tugagan"},
        )

        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(item.status, OrderItem.Status.REJECTED)
        self.assertEqual(item.rejection_reason, "Mahsulot tugagan")
        self.assertEqual(order.status, Order.Status.PARTIALLY_REJECTED)

    def test_table_bill_shows_active_orders(self):
        self.client.login(username="kassir_test", password="TestPass123!")
        waiter = Waiter.objects.create(full_name="Ali Valiyev")
        table = DiningTable.objects.create(number=105, zone="Zal")
        product = Product.objects.create(name="Choy", price=5000)
        order = Order.objects.create(external_id="MOB-1003", waiter=waiter, table=table)
        OrderItem.objects.create(order=order, product=product, quantity=2)

        response = self.client.get(reverse("orders:table_bill", args=[table.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Stol #105")
        self.assertContains(response, "10000")

    def test_close_table_marks_active_orders_completed(self):
        self.client.login(username="kassir_test", password="TestPass123!")
        waiter = Waiter.objects.create(full_name="Ali Valiyev")
        table = DiningTable.objects.create(number=106)
        product = Product.objects.create(name="Burger", price=20000)
        order = Order.objects.create(external_id="MOB-1004", waiter=waiter, table=table)
        OrderItem.objects.create(order=order, product=product, quantity=1)

        response = self.client.post(reverse("orders:close_table", args=[table.pk]))

        # close_table endi redirect emas, to'lov chekini (table_print.html) render qiladi.
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COMPLETED)
        self.assertEqual(table.assigned_waiters.count(), 0)

    def test_accept_order_assigns_waiter_to_table(self):
        self.client.login(username="kassir_test", password="TestPass123!")
        table = DiningTable.objects.create(number=109)
        product = Product.objects.create(name="Shashlik", price=25000)
        order = Order.objects.create(external_id="MOB-1007", waiter=self.waiter, table=table)
        OrderItem.objects.create(order=order, product=product, quantity=1)
        # Buyurtma qabul qilish ochiq smenani talab qiladi.
        Shift.objects.create(opened_by=self.user)

        response = self.client.post(reverse("orders:accept_order", args=[order.pk]))

        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        table.refresh_from_db()
        self.assertEqual(order.status, Order.Status.ACCEPTED)
        self.assertTrue(table.assigned_waiters.filter(pk=self.waiter_user.pk).exists())

    def test_sections_are_split_by_function(self):
        self.client.login(username="kassir_test", password="TestPass123!")
        waiter = Waiter.objects.create(full_name="Hasan")
        table = DiningTable.objects.create(number=108)
        product = Product.objects.create(name="Lavash", price=30000)
        active = Order.objects.create(external_id="MOB-1005", waiter=waiter, table=table)
        rejected = Order.objects.create(
            external_id="MOB-1006",
            waiter=waiter,
            table=table,
            status=Order.Status.PARTIALLY_REJECTED,
        )
        OrderItem.objects.create(order=active, product=product, quantity=1)
        OrderItem.objects.create(order=rejected, product=product, quantity=1, status=OrderItem.Status.REJECTED)

        dashboard_response = self.client.get(reverse("orders:dashboard"))
        orders_response = self.client.get(reverse("orders:orders_list"))
        rejected_response = self.client.get(reverse("orders:rejected_orders"))
        tables_response = self.client.get(reverse("orders:tables_overview"))

        self.assertContains(dashboard_response, "Bo'limlar bo'yicha boshqaruv")
        self.assertNotContains(dashboard_response, "Operatsion buyurtmalar")
        self.assertContains(orders_response, "Operatsion buyurtmalar")
        # external_id endi UI'da ko'rsatilmaydi (-> "Stol #N"). Faol buyurtma
        # operatsion ro'yxatda o'z tafsilot havolasi bilan ko'rinishi kerak.
        self.assertContains(orders_response, reverse("orders:order_detail", args=[active.pk]))
        # Rad etilgan buyurtma rad etilganlar bo'limida (buyurtma #id + ofitsant).
        self.assertContains(rejected_response, f"buyurtma #{rejected.id}")
        self.assertContains(rejected_response, "Hasan")
        self.assertContains(tables_response, "Stollar hisoboti")

    def test_api_login_returns_jwt_pair(self):
        response = self.client.post(
            reverse("orders:v1_login"),
            data=json.dumps({"username": "azizbek", "password": "12345"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("access", payload)
        self.assertIn("refresh", payload)
        self.assertEqual(payload["user"]["role"], "waiter")

    def test_api_v1_orders_requires_bearer_token(self):
        response = self.client.get(reverse("orders:v1_orders"))
        self.assertEqual(response.status_code, 401)

    def test_waiter_can_join_free_table(self):
        table = DiningTable.objects.create(number=110)

        login_response = self.client.post(
            reverse("orders:v1_login"),
            data=json.dumps({"username": "azizbek", "password": "12345"}),
            content_type="application/json",
        )
        token = login_response.json()["access"]
        auth = {"HTTP_AUTHORIZATION": f"Bearer {token}"}

        join_response = self.client.post(
            reverse("orders:v1_table_join", args=[table.pk]),
            data="{}",
            content_type="application/json",
            **auth,
        )

        self.assertEqual(join_response.status_code, 200)
        self.assertEqual(join_response.json()["status"], "assigned")

    def test_waiter_order_api_flow(self):
        table = DiningTable.objects.create(number=111)
        category = MenuCategory.objects.create(name="Milliy taomlar", sort_order=1)
        product = Product.objects.create(name="Pizza", price=45000, category=category)
        order = Order.objects.create(external_id="MOB-2001", waiter=self.waiter, table=table)
        OrderItem.objects.create(order=order, product=product, quantity=2)

        login_response = self.client.post(
            reverse("orders:v1_login"),
            data=json.dumps({"username": "azizbek", "password": "12345"}),
            content_type="application/json",
        )
        token = login_response.json()["access"]
        auth = {"HTTP_AUTHORIZATION": f"Bearer {token}"}

        me_response = self.client.get(reverse("orders:v1_me"), **auth)
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.json()["role"], "waiter")

        tables_response = self.client.get(reverse("orders:v1_tables"), **auth)
        self.assertEqual(tables_response.status_code, 200)
        self.assertTrue(any(row["number"] == 111 for row in tables_response.json()))

        orders_response = self.client.get(reverse("orders:v1_orders"), **auth)
        self.assertEqual(orders_response.status_code, 200)
        self.assertEqual(orders_response.json()[0]["id"], order.id)

        create_response = self.client.post(
            reverse("orders:v1_orders"),
            data=json.dumps(
                {
                    "table_id": table.id,
                    "note": "",
                    "items": [{"menu_item_id": product.id, "quantity": 1}],
                }
            ),
            content_type="application/json",
            **auth,
        )
        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.json()["waiter"]["username"], "azizbek")

        empty_response = self.client.post(
            reverse("orders:v1_orders"),
            data=json.dumps(
                {
                    "table_id": table.id,
                    "note": "",
                    "items": [],
                }
            ),
            content_type="application/json",
            **auth,
        )
        self.assertEqual(empty_response.status_code, 400)

        reject_response = self.client.post(
            reverse("orders:v1_order_cancel", args=[order.pk]),
            data=json.dumps({"reason": "Mijoz bekor qildi"}),
            content_type="application/json",
            **auth,
        )
        self.assertEqual(reject_response.status_code, 200)
        self.assertEqual(reject_response.json()["status"], "cancelled")

    def test_waiter_new_order_auto_accepts_on_open_table_bill(self):
        table = DiningTable.objects.create(number=14)
        category = MenuCategory.objects.create(name="Desert", sort_order=3)
        product = Product.objects.create(name="Tort", price=30000, category=category)
        existing_order = Order.objects.create(
            external_id="MOB-OPEN-API-1",
            waiter=self.waiter,
            table=table,
            status=Order.Status.ACCEPTED,
        )
        OrderItem.objects.create(order=existing_order, product=product, quantity=1, status=OrderItem.Status.ACCEPTED)

        login_response = self.client.post(
            reverse("orders:v1_login"),
            data=json.dumps({"username": "azizbek", "password": "12345"}),
            content_type="application/json",
        )
        token = login_response.json()["access"]
        auth = {"HTTP_AUTHORIZATION": f"Bearer {token}"}

        create_response = self.client.post(
            reverse("orders:v1_orders"),
            data=json.dumps(
                {
                    "table_id": table.id,
                    "note": "",
                    "items": [{"menu_item_id": product.id, "quantity": 2}],
                }
            ),
            content_type="application/json",
            **auth,
        )

        self.assertEqual(create_response.status_code, 201)
        created_order = Order.objects.get(pk=create_response.json()["id"])
        self.assertEqual(created_order.status, Order.Status.ACCEPTED)
        self.assertTrue(table.assigned_waiters.filter(pk=self.waiter_user.pk).exists())
        self.assertTrue(all(item.status == OrderItem.Status.ACCEPTED for item in created_order.items.all()))

    def test_api_order_external_ids_do_not_collide_under_bulk_create(self):
        table = DiningTable.objects.create(number=15)
        category = MenuCategory.objects.create(name="Fast food", sort_order=4)
        product = Product.objects.create(name="Hot dog", price=18000, category=category)

        login_response = self.client.post(
            reverse("orders:v1_login"),
            data=json.dumps({"username": "azizbek", "password": "12345"}),
            content_type="application/json",
        )
        token = login_response.json()["access"]
        auth = {"HTTP_AUTHORIZATION": f"Bearer {token}"}

        created_ids = set()
        for _ in range(75):
            response = self.client.post(
                reverse("orders:v1_orders"),
                data=json.dumps(
                    {
                        "table_id": table.id,
                        "note": "",
                        "items": [{"menu_item_id": product.id, "quantity": 1}],
                    }
                ),
                content_type="application/json",
                **auth,
            )
            self.assertEqual(response.status_code, 201)
            created_ids.add(Order.objects.get(pk=response.json()["id"]).external_id)

        self.assertEqual(len(created_ids), 75)

    def test_director_and_cashier_endpoints(self):
        table = DiningTable.objects.create(number=112, seats=4, location="Asosiy zal")
        table.assigned_waiters.add(self.waiter_user)
        category = MenuCategory.objects.create(name="Ichimliklar", sort_order=2)
        product = Product.objects.create(name="Moxito", price=22000, category=category)
        order = Order.objects.create(external_id="MOB-3001", waiter=self.waiter, table=table)
        OrderItem.objects.create(order=order, product=product, quantity=1)

        director_login = self.client.post(
            reverse("orders:v1_login"),
            data=json.dumps({"username": "director_test", "password": "Director123!"}),
            content_type="application/json",
        )
        director_token = director_login.json()["access"]
        director_auth = {"HTTP_AUTHORIZATION": f"Bearer {director_token}"}

        summary_response = self.client.get(reverse("orders:v1_dashboard_summary"), **director_auth)
        self.assertEqual(summary_response.status_code, 200)
        self.assertGreaterEqual(summary_response.json()["tables"]["total"], 1)

        waiters_response = self.client.get(reverse("orders:v1_waiters_overview"), **director_auth)
        self.assertEqual(waiters_response.status_code, 200)
        self.assertEqual(waiters_response.json()[0]["username"], "azizbek")

        reject_response = self.client.post(
            reverse("orders:v1_order_reject", args=[order.pk]),
            data=json.dumps({"reason": "Mahsulot yo'q"}),
            content_type="application/json",
            **director_auth,
        )
        self.assertEqual(reject_response.status_code, 200)
        self.assertEqual(reject_response.json()["status"], "rejected")

        cashier_login = self.client.post(
            reverse("orders:v1_login"),
            data=json.dumps({"username": "kassir_test", "password": "TestPass123!"}),
            content_type="application/json",
        )
        cashier_token = cashier_login.json()["access"]
        cashier_auth = {"HTTP_AUTHORIZATION": f"Bearer {cashier_token}"}

        payment_response = self.client.post(
            reverse("orders:v1_payments"),
            data=json.dumps(
                {
                    "order_id": order.id,
                    "payment_method": "cash",
                    "amount": "22000.00",
                }
            ),
            content_type="application/json",
            **cashier_auth,
        )
        self.assertEqual(payment_response.status_code, 201)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COMPLETED)

        duplicate_payment_response = self.client.post(
            reverse("orders:v1_payments"),
            data=json.dumps(
                {
                    "order_id": order.id,
                    "payment_method": "cash",
                    "amount": "22000.00",
                }
            ),
            content_type="application/json",
            **cashier_auth,
        )
        self.assertEqual(duplicate_payment_response.status_code, 400)

        invalid_payment_response = self.client.post(
            reverse("orders:v1_payments"),
            data=json.dumps(
                {
                    "order_id": order.id,
                    "payment_method": "cash",
                    "amount": "0.00",
                }
            ),
            content_type="application/json",
            **cashier_auth,
        )
        self.assertEqual(invalid_payment_response.status_code, 400)

        payments_response = self.client.get(reverse("orders:v1_payments"), **cashier_auth)
        self.assertEqual(payments_response.status_code, 200)
        self.assertEqual(payments_response.json()[0]["payment_method"], "cash")

    def test_payment_amount_must_match_order_total(self):
        table = DiningTable.objects.create(number=118)
        product = Product.objects.create(name="Steyk", price=40000)
        order = Order.objects.create(external_id="MOB-3010", waiter=self.waiter, table=table)
        OrderItem.objects.create(order=order, product=product, quantity=1)

        cashier_login = self.client.post(
            reverse("orders:v1_login"),
            data=json.dumps({"username": "kassir_test", "password": "TestPass123!"}),
            content_type="application/json",
        )
        cashier_auth = {"HTTP_AUTHORIZATION": f"Bearer {cashier_login.json()['access']}"}

        payment_response = self.client.post(
            reverse("orders:v1_payments"),
            data=json.dumps(
                {
                    "order_id": order.id,
                    "payment_method": "cash",
                    "amount": "39000.00",
                }
            ),
            content_type="application/json",
            **cashier_auth,
        )
        self.assertEqual(payment_response.status_code, 400)
        self.assertEqual(payment_response.json()["expected_amount"], 40000.0)

    def test_mobile_platform_api_paths_are_supported(self):
        director_login = self.client.post(
            reverse("orders:api_login"),
            data=json.dumps({"username": "director_test", "password": "Director123!"}),
            content_type="application/json",
            HTTP_ORIGIN="http://localhost:5173",
        )
        self.assertEqual(director_login.status_code, 200)
        self.assertEqual(director_login["access-control-allow-origin"], "http://localhost:5173")
        director_auth = {"HTTP_AUTHORIZATION": f"Bearer {director_login.json()['access']}"}

        me_response = self.client.get(reverse("orders:api_me"), **director_auth)
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.json()["role"], "director")

        table_response = self.client.post(
            reverse("orders:api_staff_tables"),
            data=json.dumps({"number": 21, "zone": "Zal", "seats": 4, "location": "Asosiy zal"}),
            content_type="application/json",
            **director_auth,
        )
        self.assertEqual(table_response.status_code, 201)
        table_id = table_response.json()["id"]

        tables_response = self.client.get(reverse("orders:api_staff_tables"), **director_auth)
        self.assertEqual(tables_response.status_code, 200)
        self.assertTrue(any(row["number"] == 21 for row in tables_response.json()))

        category_response = self.client.post(
            reverse("orders:api_staff_menu_categories"),
            data=json.dumps({"name": "Mobil kategoriya", "sort_order": 1}),
            content_type="application/json",
            **director_auth,
        )
        self.assertEqual(category_response.status_code, 201)
        category_id = category_response.json()["id"]

        item_response = self.client.post(
            reverse("orders:api_staff_menu_items"),
            data=json.dumps(
                {
                    "name": "Mobil taom",
                    "category_id": category_id,
                    "description": "",
                    "price": "15000.00",
                    "is_active": True,
                }
            ),
            content_type="application/json",
            **director_auth,
        )
        self.assertEqual(item_response.status_code, 201)
        item_id = item_response.json()["id"]

        waiter_login = self.client.post(
            reverse("orders:api_login"),
            data=json.dumps({"username": "azizbek", "password": "12345"}),
            content_type="application/json",
        )
        self.assertEqual(waiter_login.status_code, 200)
        waiter_auth = {"HTTP_AUTHORIZATION": f"Bearer {waiter_login.json()['access']}"}

        order_response = self.client.post(
            reverse("orders:api_staff_orders"),
            data=json.dumps(
                {
                    "table_id": table_id,
                    "note": "Mobil platformadan",
                    "items": [{"menu_item_id": item_id, "quantity": 2}],
                }
            ),
            content_type="application/json",
            **waiter_auth,
        )
        self.assertEqual(order_response.status_code, 201)
        order_id = order_response.json()["id"]

        orders_response = self.client.get(reverse("orders:api_staff_orders"), **waiter_auth)
        self.assertEqual(orders_response.status_code, 200)
        self.assertTrue(any(row["id"] == order_id for row in orders_response.json()))

        reject_response = self.client.post(
            reverse("orders:api_staff_order_reject", args=[order_id]),
            data=json.dumps({"reason": "Test rad etish"}),
            content_type="application/json",
            **director_auth,
        )
        self.assertEqual(reject_response.status_code, 200)
        self.assertEqual(reject_response.json()["status"], "rejected")

        cashier_login = self.client.post(
            reverse("orders:api_login"),
            data=json.dumps({"username": "kassir_test", "password": "TestPass123!"}),
            content_type="application/json",
        )
        self.assertEqual(cashier_login.status_code, 200)
        cashier_auth = {"HTTP_AUTHORIZATION": f"Bearer {cashier_login.json()['access']}"}

        payment_response = self.client.post(
            reverse("orders:api_cashier_payments"),
            data=json.dumps({"order_id": order_id, "payment_method": "cash", "amount": "30000.00"}),
            content_type="application/json",
            **cashier_auth,
        )
        self.assertEqual(payment_response.status_code, 201)
        payment_id = payment_response.json()["id"]

        payment_detail_response = self.client.get(reverse("orders:api_cashier_payment_detail", args=[payment_id]), **cashier_auth)
        self.assertEqual(payment_detail_response.status_code, 200)
        self.assertEqual(payment_detail_response.json()["order_id"], order_id)

        payment_patch_response = self.client.patch(
            reverse("orders:api_cashier_payment_detail", args=[payment_id]),
            data=json.dumps({"payment_method": "card", "amount": "30001.00"}),
            content_type="application/json",
            **cashier_auth,
        )
        self.assertEqual(payment_patch_response.status_code, 200)
        self.assertEqual(payment_patch_response.json()["payment_method"], "card")
        self.assertEqual(payment_patch_response.json()["amount"], 30001.0)

        dashboard_response = self.client.get(reverse("orders:api_dashboard_summary"), **director_auth)
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertIn("tables", dashboard_response.json())


class NewEndpointTests(TestCase):
    """Yangi API endpoint'lar uchun testlar."""

    def setUp(self):
        self.client = Client()
        User = get_user_model()
        # Director
        self.director_user = User.objects.create_user(username="director2", password="Dir123!")
        UserProfile.objects.create(user=self.director_user, full_name="Director Test", role=UserProfile.Role.DIRECTOR)
        # Cashier
        self.cashier_user = User.objects.create_user(username="kassir2", password="Kas123!")
        UserProfile.objects.create(user=self.cashier_user, full_name="Kassir Test", role=UserProfile.Role.CASHIER)
        # Waiter
        self.waiter_user = User.objects.create_user(username="ofitsant2", password="Ofi123!")
        UserProfile.objects.create(user=self.waiter_user, full_name="Ofitsant Test", role=UserProfile.Role.WAITER)
        self.waiter = Waiter.objects.create(user=self.waiter_user, full_name="Ofitsant Test")
        # Data
        self.table = DiningTable.objects.create(number=50, seats=4)
        self.category = MenuCategory.objects.create(name="Test Kategoriya", sort_order=1)
        self.product = Product.objects.create(name="Test Taom", price=25000, category=self.category, is_rejectable=True)
        self.product_fixed = Product.objects.create(name="Doimiy Taom", price=10000, category=self.category, is_rejectable=False)

    def _login(self, username, password):
        r = self.client.post(
            reverse("orders:v1_login"),
            data=json.dumps({"username": username, "password": password}),
            content_type="application/json",
        )
        return {"HTTP_AUTHORIZATION": f"Bearer {r.json()['access']}"}

    def test_director_waiter_crud(self):
        auth = self._login("director2", "Dir123!")
        # Create
        r = self.client.post(
            reverse("orders:v1_director_waiters"),
            data=json.dumps({"username": "yangi_of", "password": "1234", "full_name": "Yangi Ofitsant", "phone": "+998"}),
            content_type="application/json", **auth,
        )
        self.assertEqual(r.status_code, 201)
        user_id = r.json()["id"]
        # List
        r = self.client.get(reverse("orders:v1_director_waiters"), **auth)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(any(w["username"] == "yangi_of" for w in r.json()))
        # Update
        r = self.client.patch(
            reverse("orders:v1_director_waiter_detail", args=[user_id]),
            data=json.dumps({"full_name": "Yangilangan Ism"}),
            content_type="application/json", **auth,
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["full_name"], "Yangilangan Ism")
        # Delete (deactivate)
        r = self.client.delete(reverse("orders:v1_director_waiter_detail", args=[user_id]), **auth)
        self.assertEqual(r.status_code, 204)

    def test_director_revenue_report(self):
        auth = self._login("director2", "Dir123!")
        r = self.client.get(reverse("orders:v1_director_revenue") + "?period=daily", **auth)
        self.assertEqual(r.status_code, 200)
        self.assertIn("totals", r.json())
        r = self.client.get(reverse("orders:v1_director_revenue") + "?period=weekly", **auth)
        self.assertEqual(r.status_code, 200)

    def test_director_qr_code(self):
        auth = self._login("director2", "Dir123!")
        r = self.client.get(reverse("orders:v1_table_qr", args=[self.table.pk]), **auth)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "image/png")

    def test_cashier_daily_stock(self):
        auth = self._login("kassir2", "Kas123!")
        # Portsiya kiritish ochiq smenani talab qiladi.
        Shift.objects.create(opened_by=self.cashier_user)
        # Set stock
        r = self.client.post(
            reverse("orders:v1_daily_stock"),
            data=json.dumps({"stocks": [{"product_id": self.product.id, "initial_quantity": 50}]}),
            content_type="application/json", **auth,
        )
        self.assertEqual(r.status_code, 200)
        # Get stock
        r = self.client.get(reverse("orders:v1_daily_stock"), **auth)
        self.assertEqual(r.status_code, 200)
        item = next(i for i in r.json() if i["product_id"] == self.product.id)
        self.assertEqual(item["initial_quantity"], 50)
        self.assertEqual(item["remaining_quantity"], 50)

    def test_cashier_daily_stock_update_preserves_consumed_quantity(self):
        auth = self._login("kassir2", "Kas123!")
        # Portsiya kiritish ochiq smenani talab qiladi.
        Shift.objects.create(opened_by=self.cashier_user)
        self.client.post(
            reverse("orders:v1_daily_stock"),
            data=json.dumps({"stocks": [{"product_id": self.product.id, "initial_quantity": 10}]}),
            content_type="application/json",
            **auth,
        )
        stock = ProductDailyStock.objects.get(product=self.product)
        stock.remaining_quantity = 4
        stock.save(update_fields=["remaining_quantity"])

        response = self.client.post(
            reverse("orders:v1_daily_stock"),
            data=json.dumps({"stocks": [{"product_id": self.product.id, "initial_quantity": 12}]}),
            content_type="application/json",
            **auth,
        )

        self.assertEqual(response.status_code, 200)
        stock.refresh_from_db()
        self.assertEqual(stock.initial_quantity, 12)
        self.assertEqual(stock.remaining_quantity, 6)

    def test_cashier_accept_order(self):
        auth = self._login("kassir2", "Kas123!")
        # Buyurtma qabul qilish ochiq smenani talab qiladi.
        Shift.objects.create(opened_by=self.cashier_user)
        order = Order.objects.create(external_id="CASH-TEST-1", waiter=self.waiter, table=self.table, status=Order.Status.NEW)
        OrderItem.objects.create(order=order, product=self.product, quantity=1)
        r = self.client.post(reverse("orders:v1_cashier_accept", args=[order.pk]), content_type="application/json", **auth)
        self.assertEqual(r.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.ACCEPTED)

    def test_cashier_pending_orders(self):
        auth = self._login("kassir2", "Kas123!")
        Order.objects.create(external_id="PEND-1", waiter=self.waiter, table=self.table, status=Order.Status.NEW)
        r = self.client.get(reverse("orders:v1_cashier_pending"), **auth)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(len(r.json()) >= 1)

    def test_public_menu_via_qr(self):
        self.table.refresh_from_db()
        r = self.client.get(reverse("orders:v1_public_menu", args=[self.table.qr_token]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["table"]["number"], 50)
        self.assertTrue(len(r.json()["categories"]) >= 1)

    def test_client_self_service_order(self):
        self.table.refresh_from_db()
        r = self.client.post(
            reverse("orders:v1_public_order", args=[self.table.qr_token]),
            data=json.dumps({
                "client_name": "Alisher",
                "note": "Tez tayyorlang",
                "items": [{"menu_item_id": self.product.id, "quantity": 2, "note": "Tuzsiz"}],
            }),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["client_name"], "Alisher")
        self.assertEqual(r.json()["table_number"], 50)
        self.assertIn("public_token", r.json())
        order = Order.objects.get(pk=r.json()["id"])
        self.assertEqual(order.order_source, Order.OrderSource.CLIENT)
        self.assertIsNone(order.waiter)

    def test_each_client_scan_gets_separate_bill(self):
        """Bitta stolda har bir mijoz (qurilma) alohida shot (hisob) oladi —
        buyurtmalar bir-biriga qo'shilib ketmaydi."""
        self.table.refresh_from_db()

        def order_as(name):
            return self.client.post(
                reverse("orders:v1_public_order", args=[self.table.qr_token]),
                data=json.dumps({
                    "client_name": name,
                    "items": [{"menu_item_id": self.product.id, "quantity": 1}],
                }),
                content_type="application/json",
            )

        r1 = order_as("Aziz")
        r2 = order_as("Bobur")
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)

        o1 = Order.objects.get(pk=r1.json()["id"])
        o2 = Order.objects.get(pk=r2.json()["id"])
        # Turli shot raqamlari — alohida hisoblar.
        self.assertNotEqual(o1.bill_number, o2.bill_number)

        # Kassada ham alohida shot bo'lib ko'rinadi.
        from .services import table_summary
        shots = table_summary(self.table)["shots"]
        client_shots = {
            o.client_name: shot["bill_number"]
            for shot in shots
            for o in shot["orders"]
            if o.order_source == Order.OrderSource.CLIENT
        }
        self.assertEqual(client_shots.get("Aziz"), o1.bill_number)
        self.assertEqual(client_shots.get("Bobur"), o2.bill_number)
        self.assertNotEqual(client_shots["Aziz"], client_shots["Bobur"])

    def test_public_order_status_requires_token(self):
        self.table.refresh_from_db()
        create_response = self.client.post(
            reverse("orders:v1_public_order", args=[self.table.qr_token]),
            data=json.dumps({
                "client_name": "Alisher",
                "items": [{"menu_item_id": self.product.id, "quantity": 1}],
            }),
            content_type="application/json",
        )
        order_id = create_response.json()["id"]
        token = create_response.json()["public_token"]

        no_token_response = self.client.get(reverse("orders:v1_public_order_status", args=[order_id]))
        self.assertEqual(no_token_response.status_code, 400)

        response = self.client.get(f"{reverse('orders:v1_public_order_status', args=[order_id])}?token={token}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], order_id)

    def test_public_reject_item_requires_matching_token(self):
        self.table.refresh_from_db()
        create_response = self.client.post(
            reverse("orders:v1_public_order", args=[self.table.qr_token]),
            data=json.dumps({
                "client_name": "Alisher",
                "items": [{"menu_item_id": self.product.id, "quantity": 1}],
            }),
            content_type="application/json",
        )
        order = Order.objects.get(pk=create_response.json()["id"])
        item = order.items.get()

        response = self.client.post(
            reverse("orders:v1_public_reject_item", args=[order.id, item.id]),
            data=json.dumps({"reason": "Bekor", "token": "wrong-token"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_cashier_tables_overview_api(self):
        auth = self._login("kassir2", "Kas123!")
        order = Order.objects.create(external_id="OVERVIEW-1", waiter=self.waiter, table=self.table, status=Order.Status.ACCEPTED)
        OrderItem.objects.create(order=order, product=self.product, quantity=2, status=OrderItem.Status.ACCEPTED)

        response = self.client.get(reverse("orders:v1_cashier_tables_overview"), **auth)

        self.assertEqual(response.status_code, 200)
        table_payload = next(item for item in response.json() if item["table"]["number"] == 50)
        self.assertEqual(table_payload["orders_count"], 1)
        self.assertEqual(table_payload["shots"][0]["bill_number"], 1)

    def test_stock_capacity_blocks_order(self):
        """Sig'im 0 bo'lsa buyurtma berib bo'lmasligi."""
        from django.utils import timezone
        ProductDailyStock.objects.create(
            product=self.product, date=timezone.localdate(),
            initial_quantity=1, remaining_quantity=0, set_by=self.cashier_user,
        )
        self.table.refresh_from_db()
        r = self.client.post(
            reverse("orders:v1_public_order", args=[self.table.qr_token]),
            data=json.dumps({
                "client_name": "Test Mijoz",
                "items": [{"menu_item_id": self.product.id, "quantity": 1}],
            }),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_is_rejectable_in_menu(self):
        """Menyu'da is_rejectable ko'rinishi."""
        self.table.refresh_from_db()
        r = self.client.get(reverse("orders:v1_public_menu", args=[self.table.qr_token]))
        cats = r.json()["categories"]
        items = []
        for c in cats:
            items.extend(c["items"])
        rejectable = next((i for i in items if i["id"] == self.product.id), None)
        fixed = next((i for i in items if i["id"] == self.product_fixed.id), None)
        self.assertIsNotNone(rejectable)
        self.assertTrue(rejectable["is_rejectable"])
        self.assertIsNotNone(fixed)
        self.assertFalse(fixed["is_rejectable"])

    def test_waiter_all_tables(self):
        auth = self._login("ofitsant2", "Ofi123!")
        r = self.client.get(reverse("orders:v1_waiter_all_tables"), **auth)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(any(t["number"] == 50 for t in r.json()))

# Create your tests here.
