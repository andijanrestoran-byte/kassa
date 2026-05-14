from decimal import Decimal

from django.db import migrations


DEFAULT_TABLES = [
    {"number": 1, "zone": "Asosiy zal", "seats": 4, "location": "Kirish tomoni"},
    {"number": 2, "zone": "Asosiy zal", "seats": 4, "location": "Kirish tomoni"},
    {"number": 3, "zone": "Asosiy zal", "seats": 4, "location": "Markaz"},
    {"number": 4, "zone": "Asosiy zal", "seats": 4, "location": "Markaz"},
    {"number": 5, "zone": "Asosiy zal", "seats": 6, "location": "Oyna yonida"},
    {"number": 6, "zone": "Asosiy zal", "seats": 6, "location": "Oyna yonida"},
    {"number": 7, "zone": "Oilaviy xona", "seats": 8, "location": "Chap qanot"},
    {"number": 8, "zone": "Oilaviy xona", "seats": 8, "location": "O'ng qanot"},
    {"number": 9, "zone": "Ayvon", "seats": 4, "location": "Tashqi qator"},
    {"number": 10, "zone": "Ayvon", "seats": 4, "location": "Tashqi qator"},
    {"number": 11, "zone": "Ayvon", "seats": 6, "location": "Burchak"},
    {"number": 12, "zone": "VIP", "seats": 10, "location": "Yopiq xona"},
]

DEFAULT_CATEGORIES = [
    {
        "name": "Milliy taomlar",
        "sort_order": 1,
        "items": [
            {"name": "Palov", "price": Decimal("35000.00"), "description": "Andijoncha palov"},
            {"name": "Lag'mon", "price": Decimal("28000.00"), "description": "Qo'lda tortilgan lag'mon"},
            {"name": "Manti", "price": Decimal("24000.00"), "description": "Go'shtli manti"},
        ],
    },
    {
        "name": "Fast food",
        "sort_order": 2,
        "items": [
            {"name": "Lavash", "price": Decimal("28000.00"), "description": "Mol go'shtli lavash"},
            {"name": "Burger", "price": Decimal("30000.00"), "description": "Klassik burger"},
            {"name": "Hot-dog", "price": Decimal("18000.00"), "description": "Sousli hot-dog"},
        ],
    },
    {
        "name": "Ichimliklar",
        "sort_order": 3,
        "items": [
            {"name": "Choy", "price": Decimal("5000.00"), "description": "Ko'k choy"},
            {"name": "Coca-Cola 1L", "price": Decimal("12000.00"), "description": "Sovuq ichimlik"},
            {"name": "Moxito", "price": Decimal("22000.00"), "description": "Muzdek moxito"},
        ],
    },
    {
        "name": "Salatlar",
        "sort_order": 4,
        "items": [
            {"name": "Sezar", "price": Decimal("26000.00"), "description": "Tovuqli sezar"},
            {"name": "Achichuk", "price": Decimal("12000.00"), "description": "Yangi pomidor salati"},
        ],
    },
    {
        "name": "Desertlar",
        "sort_order": 5,
        "items": [
            {"name": "Tort", "price": Decimal("30000.00"), "description": "Kunlik desert"},
            {"name": "Muzqaymoq", "price": Decimal("15000.00"), "description": "Vanilli muzqaymoq"},
        ],
    },
]


def seed_tables_and_menu(apps, schema_editor):
    DiningTable = apps.get_model("orders", "DiningTable")
    MenuCategory = apps.get_model("orders", "MenuCategory")
    Product = apps.get_model("orders", "Product")

    for table_payload in DEFAULT_TABLES:
        DiningTable.objects.update_or_create(
            number=table_payload["number"],
            defaults={
                "zone": table_payload["zone"],
                "seats": table_payload["seats"],
                "location": table_payload["location"],
            },
        )

    for category_payload in DEFAULT_CATEGORIES:
        category, _ = MenuCategory.objects.update_or_create(
            name=category_payload["name"],
            defaults={"sort_order": category_payload["sort_order"]},
        )
        for item_payload in category_payload["items"]:
            Product.objects.update_or_create(
                name=item_payload["name"],
                category=category,
                defaults={
                    "description": item_payload["description"],
                    "price": item_payload["price"],
                    "is_active": True,
                },
            )


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0010_seed_mobile_users"),
    ]

    operations = [
        migrations.RunPython(seed_tables_and_menu, migrations.RunPython.noop),
    ]
