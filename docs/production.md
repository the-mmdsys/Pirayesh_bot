# Production Notes

این فایل برای آماده سازی Production است، نه انتخاب هاست یا انجام Deploy واقعی.

## Development vs Production

در Development راحتی مهم است: `DJANGO_DEBUG=True`، اجرای `runserver`، و Long Polling با `python bot.py`.

در Production امنیت و پایداری مهم است: `DJANGO_DEBUG=False`، اجرای Django پشت یک application server و reverse proxy، HTTPS، logging، backup و webhook.

## Environment Variables

نمونه متغیرها در `.env.example` قرار دارد. مقدار واقعی secretها فقط باید داخل `.env` یا environment سرور باشد.

- `BALE_BOT_TOKEN`
- `BALE_WEBHOOK_SECRET`
- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DJANGO_STATIC_ROOT`
- `DJANGO_MEDIA_URL`
- `DJANGO_MEDIA_ROOT`
- `DJANGO_LOG_LEVEL`
- `DJANGO_LOG_DIR`
- `DJANGO_SECURE_SSL_REDIRECT`
- `DJANGO_SESSION_COOKIE_SECURE`
- `DJANGO_CSRF_COOKIE_SECURE`
- `DJANGO_SECURE_HSTS_SECONDS`
- `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS`
- `DJANGO_SECURE_HSTS_PRELOAD`
- `DJANGO_SECURE_CONTENT_TYPE_NOSNIFF`
- `DJANGO_USE_X_FORWARDED_PROTO`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `DB_HOST`
- `DB_PORT`

برای چند host یا origin از کاما استفاده کن:

```env
DJANGO_ALLOWED_HOSTS=example.com,www.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://example.com,https://www.example.com
```

## Database

دیتابیس اصلی پروژه PostgreSQL است. در Production مقدار `DB_HOST` بسته به محل اجرای PostgreSQL تعیین می شود و ممکن است `localhost` نباشد.

قبل از اجرای نسخه جدید:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
```

## Static Files

Static یعنی فایل های ثابت پروژه، مثل CSS و JavaScript و تصویرهای ثابت خود برنامه.

در Production باید collectstatic اجرا شود:

```powershell
.\.venv\Scripts\python.exe manage.py collectstatic
```

خروجی داخل `DJANGO_STATIC_ROOT` قرار می گیرد. سرو کردن این فایل ها باید توسط reverse proxy یا وب سرور Production انجام شود.

Tailwind CDN پنل فعلاً طبق تصمیم پروژه تغییر نکرده است.

## Media Files

Media یعنی فایل هایی که کاربر یا ادمین upload می کند، مثل تصویر آرایشگر.

در Development خود Django با `DEBUG=True` می تواند media را سرو کند. در Production باید media توسط وب سرور، volume پایدار، یا storage مناسب سرو شود. فعلاً هیچ provider خاصی انتخاب نشده است.

## Security

برای Production معمولاً این مقدارها لازم می شوند:

```env
DJANGO_DEBUG=False
DJANGO_SECURE_SSL_REDIRECT=True
DJANGO_SESSION_COOKIE_SECURE=True
DJANGO_CSRF_COOKIE_SECURE=True
DJANGO_SECURE_HSTS_SECONDS=31536000
DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=True
DJANGO_SECURE_HSTS_PRELOAD=True
DJANGO_SECURE_CONTENT_TYPE_NOSNIFF=True
```

HSTS و redirect به HTTPS فقط وقتی فعال شوند که HTTPS واقعی و درست روی دامنه تنظیم شده باشد.

## Logging

Logها در مسیر `DJANGO_LOG_DIR` ذخیره می شوند. مقدار پیش فرض `logs/` است.

- `logs/django.log`
- `logs/bale_bot.log`

فیلتر logging مقدارهای حساس مثل token، password دیتابیس و secret key را redaction می کند. با این حال نباید این مقدارها را خودمان عمداً وارد messageهای log کنیم.

## Bale Long Polling

Development همچنان با Long Polling کار می کند:

```powershell
.\.venv\Scripts\python.exe bot.py
```

مسیر فعلی:

```text
Bale getUpdates -> polling -> handle_update -> flowهای موجود
```

## Bale Webhook

Webhook جدید فقط transport است و business logic را دوباره ننوشته است:

```text
Bale -> HTTPS POST /bale/webhook/ -> handle_update -> flowهای موجود
```

اگر secret تنظیم شود، endpoint مقدار header زیر را بررسی می کند:

```text
X-Bale-Webhook-Secret
```

جزئیات قطعی setWebhook و روش رسمی اعتبارسنجی باید طبق مستندات Bale در زمان اتصال نهایی بررسی شود.

## Health Check

برای بررسی بالا بودن Django:

```text
GET /health/
```

خروجی:

```json
{"status": "ok"}
```

## PostgreSQL Backup

Backup نمونه:

```powershell
pg_dump -h DB_HOST -p DB_PORT -U DB_USER -F c -f backup.dump DB_NAME
```

Restore نمونه:

```powershell
pg_restore -h DB_HOST -p DB_PORT -U DB_USER -d DB_NAME --clean --if-exists backup.dump
```

Password را داخل command ننویس. بهتر است از prompt امن PostgreSQL یا تنظیمات امن محیط سرور استفاده شود.

Backup باید دوره ای باشد و Restore آن هم تست شود؛ backup تست نشده قابل اعتماد نیست.

## Simple Production Architecture

```text
Internet
-> HTTPS / Reverse Proxy
-> Django Application Server
-> Django
-> PostgreSQL
```

برای Bale:

```text
Bale
-> HTTPS Webhook
-> Django /bale/webhook/
-> Existing Handler
```

`python manage.py runserver` برای Production مناسب نیست، چون برای توسعه ساخته شده و جایگزین application server و وب سرور Production نیست.

## Checklist

- `DJANGO_DEBUG=False`
- `DJANGO_SECRET_KEY` امن و محرمانه
- `DJANGO_ALLOWED_HOSTS` درست
- `DJANGO_CSRF_TRUSTED_ORIGINS` با scheme کامل
- HTTPS فعال
- security flags مناسب HTTPS فعال
- PostgreSQL آماده و بکاپ گرفته شده
- migration اجرا شده
- `collectstatic` اجرا شده
- media volume یا مسیر پایدار آماده
- logها بررسی پذیر و خارج از Git
- admin URL و حساب های admin امن
- `BALE_BOT_TOKEN` محرمانه
- webhook روی HTTPS تنظیم شده
- Long Polling روی Production همزمان با webhook اجرا نشود
- environment variables کامل
- testها قبل از انتشار سبز
