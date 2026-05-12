# Dasturxon Web Ilovasi

Bu loyiha Django asosida yozilgan restoran backend va boshqaruv paneli.

## Ishga tushirish

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

## API

Base path:

`/api/v1`

Mobil/web platforma uchun moslik base path:

`/api`

Auth:

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `GET /api/v1/auth/me`

Authorization header:

`Authorization: Bearer <access_token>`

Roles:

- `waiter`
- `director`
- `cashier`

Asosiy endpointlar:

- `GET /api/v1/tables`
- `POST /api/v1/tables/{table_id}/join`
- `GET /api/v1/menu/categories`
- `POST /api/v1/menu/categories`
- `PATCH /api/v1/menu/categories/{id}`
- `DELETE /api/v1/menu/categories/{id}`
- `GET /api/v1/menu/items`
- `POST /api/v1/menu/items`
- `PATCH /api/v1/menu/items/{id}`
- `DELETE /api/v1/menu/items/{id}`
- `POST /api/v1/orders`
- `GET /api/v1/orders`
- `GET /api/v1/orders/{id}`
- `POST /api/v1/orders/{id}/reject`
- `POST /api/v1/orders/{id}/cancel`
- `POST /api/v1/payments`
- `GET /api/v1/payments`
- `GET /api/v1/dashboard/summary`
- `GET /api/v1/waiters/overview`

Qo'shimcha moslik endpointi:

- `POST /api/mobile-orders/`

Mobil/web platforma endpointlari:

- `POST /api/auth/login/`
- `POST /api/auth/refresh/`
- `GET /api/auth/me/`
- `GET|POST /api/staff/menu/items/`
- `GET|PATCH|DELETE /api/staff/menu/items/{id}/`
- `GET|POST /api/staff/menu/categories/`
- `GET|PATCH|DELETE /api/staff/menu/categories/{id}/`
- `GET|POST /api/staff/orders/`
- `POST /api/staff/orders/{id}/reject/`
- `POST /api/staff/orders/{id}/cancel/`
- `GET|POST /api/cashier/payments/`
- `GET|PATCH /api/cashier/payments/{id}/`
- `GET /api/dashboard/summary/`
- `GET|POST /api/staff/tables/`

Frontend `.env`:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000/api
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000/api
```

Backend `.env`:

```env
DEBUG=True
SECRET_KEY=change-me-in-production
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000
CSRF_TRUSTED_ORIGINS=
```

Railway Postgres uchun app service variables ichida `DATABASE_URL` ni Postgres service qiymatiga ulang:

```env
DATABASE_URL=${{Postgres.DATABASE_URL}}
```

Deploy start command namunasi:

```bash
python manage.py migrate && python manage.py collectstatic --noinput && gunicorn config.wsgi:application
```

## JWT login namunasi

Request:

```json
{
  "username": "azizbek",
  "password": "12345"
}
```

Response:

```json
{
  "access": "jwt_access_token",
  "refresh": "jwt_refresh_token",
  "user": {
    "id": 7,
    "username": "azizbek",
    "full_name": "Azizbek Karimov",
    "role": "waiter"
  }
}
```
