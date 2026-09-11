<<<<<<< HEAD
# ربات نوبت‌دهی آرایشگاه در بله

این پروژه یک سامانه نوبت‌دهی آرایشگاه بر پایه Django و ربات پیام‌رسان بله است. مشتری می‌تواند پروفایل خود را تکمیل کند، آرایشگر و زمان آزاد را ببیند، نوبت بگیرد و نوبت‌های آینده‌اش را لغو کند. کارکنان نیز از طریق پنل وب، نوبت‌ها، آرایشگران، برنامه‌های کاری و زمان‌های مسدود را مدیریت می‌کنند.

## قابلیت‌ها

- ثبت و ویرایش مشخصات مشتری در ربات بله
- رزرو و لغو نوبت با جلوگیری از رزرو هم‌زمان یک بازه
- محاسبه زمان‌های آزاد بر اساس برنامه آرایشگر، زمان استراحت و زمان‌های مسدود
- نمایش و دریافت تاریخ شمسی
- پنل مخصوص کاربران staff برای مدیریت آرایشگاه
- اجرای ربات به دو روش Long Polling و Webhook
- Health Check و ثبت log مجزای Django و ربات

## فناوری‌ها و پیش‌نیازها

- Python 3.10 یا جدیدتر (نسخه 3.12 پیشنهاد می‌شود)
- PostgreSQL
- توکن ربات بله برای اجرای قابلیت‌های ربات

وابستگی‌های Python در فایل `requirement.txt` قرار دارند.

## راه‌اندازی در Windows (PowerShell)

ابتدا در پوشه پروژه یک محیط مجازی بسازید و وابستگی‌ها را نصب کنید:

```powershell
python -m venv venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirement.txt
```

فایل تنظیمات محیطی را بسازید:

```powershell
Copy-Item .env.example .env
```

سپس مقادیر `.env` را متناسب با محیط خود تکمیل کنید. برای ساخت یک کلید امن Django می‌توانید از دستور زیر استفاده کنید:

```powershell
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

نمونه حداقلی تنظیمات توسعه:

```env
BALE_BOT_TOKEN=your-bale-bot-token
BALE_WEBHOOK_SECRET=your-random-webhook-secret

DJANGO_SECRET_KEY=your-long-random-secret-key
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

DB_NAME=pirayesh_bot
DB_USER=postgres
DB_PASSWORD=your-database-password
DB_HOST=localhost
DB_PORT=5432
```

پایگاه داده و کاربر درج‌شده در `.env` باید از قبل در PostgreSQL ساخته شده باشند و کاربر مجوز ساخت جدول در آن پایگاه داده را داشته باشد. فایل واقعی `.env` را commit نکنید.

در ادامه migrationها را اجرا و حساب مدیر را ایجاد کنید:

```powershell
python manage.py migrate
python manage.py createsuperuser
```

وب‌سایت و ربات بله را با یک فرمان اجرا کنید. فرمان سفارشی `runserver`، پنل Django و Long Polling ربات را هم‌زمان بالا می‌آورد:

```powershell
python manage.py runserver
```

مسیرهای مهم پس از اجرا:

- پنل مدیریت پروژه: <http://127.0.0.1:8000/panel/>
- مدیریت پیش‌فرض Django: <http://127.0.0.1:8000/admin/>
- بررسی سلامت سرویس: <http://127.0.0.1:8000/health/>
- ورودی Webhook بله: `POST /bale/webhook/`

ورود به پنل پروژه فقط برای کاربران دارای دسترسی `staff` امکان‌پذیر است. حساب ساخته‌شده با `createsuperuser` این دسترسی را دارد.

برای آماده‌سازی و اجرای خودکار پروژه در Windows می‌توانید فایل زیر را اجرا کنید:

```powershell
.\start_project.bat
```

این فایل در صورت نیاز پوشه `venv` را می‌سازد، محیط را فعال می‌کند، وابستگی‌ها و migrationها را آماده می‌کند، پنل را در مرورگر باز می‌کند و سرور را روی `0.0.0.0:8000` اجرا می‌کند.

## اجرای ربات بله

در محیط توسعه اجرای `python manage.py runserver` برای راه‌اندازی Long Polling کافی است. فایل `bot.py` فقط برای اجرای مستقل ربات بدون پنل باقی مانده است:

```powershell
python bot.py
```

`bot.py` را هم‌زمان با `runserver` اجرا نکنید، چون برای هر توکن فقط یک مصرف‌کننده Long Polling باید فعال باشد.

فایل `receive_messages.py` نیز برای مشاهده خام پیام‌ها و callbackهای دریافتی قابل استفاده است:

```powershell
python receive_messages.py
```

در production معمولاً Webhook انتخاب مناسب‌تری است. Long Polling و Webhook را برای یک ربات به‌صورت هم‌زمان اجرا نکنید. اگر `BALE_WEBHOOK_SECRET` تنظیم شده باشد، درخواست Webhook باید همان مقدار را در header زیر ارسال کند:

```text
X-Bale-Webhook-Secret
```

## اجرای تست‌ها

برای اجرای تمام تست‌های پروژه:

```powershell
python manage.py test
```

برای بررسی تنظیمات استقرار:

```powershell
python manage.py check --deploy
```

دستور دوم باید با تنظیمات production، از جمله `DJANGO_DEBUG=False` و گزینه‌های امنیتی مناسب HTTPS اجرا شود؛ هشدارهای آن در محیط توسعه طبیعی است.

## ساختار پروژه

```text
appointments/       مدل‌ها، فرم‌ها و منطق زمان‌های آزاد و نوبت‌ها
bale_bot/           کلاینت API بله، handlerها، flowها، polling و webhook
config/             تنظیمات، URLهای اصلی، logging، WSGI و ASGI
panel/              پنل تحت وب کارکنان آرایشگاه
docs/production.md  راهنمای تکمیلی آماده‌سازی production
bot.py              نقطه ورود ربات در حالت Long Polling
manage.py           ابزار مدیریتی Django
```

## استقرار

`runserver` فقط برای توسعه است. در محیط واقعی باید Django پشت یک application server و reverse proxy مجهز به HTTPS اجرا شود، فایل‌های static با `collectstatic` آماده شوند و فایل‌های media و PostgreSQL روی فضای پایدار قرار بگیرند.

جزئیات متغیرهای امنیتی، logging، static/media، Webhook و تهیه نسخه پشتیبان PostgreSQL در [راهنمای production](docs/production.md) آمده است.
=======
# ✂️ Haircut Project (سیستم مدیریت و رزرو نوبت آرایشگاه)

<div align="center">
  <img src="https://via.placeholder.com/800x300?text=Haircut+Project+Banner" alt="Project Banner" width="100%">
</div>

<p align="center">
  <strong>یک پلتفرم مدرن، سریع و هوشمند برای مدیریت سالن‌های زیبایی و رزرو آنلاین نوبت.</strong>
</p>

<p align="center">
  <a href="https://github.com/mohaaasan/haircut_project/issues"><img src="https://img.shields.io/github/issues/mohaaasan/haircut_project?style=for-the-badge&color=orange" alt="Issues"></a>
  <a href="https://github.com/mohaaasan/haircut_project/network/members"><img src="https://img.shields.io/github/forks/mohaaasan/haircut_project?style=for-the-badge&color=blue" alt="Forks"></a>
  <a href="https://github.com/mohaaasan/haircut_project/stargazers"><img src="https://img.shields.io/github/stars/mohaaasan/haircut_project?style=for-the-badge&color=yellow" alt="Stars"></a>
  <a href="https://github.com/mohaaasan/haircut_project/blob/main/LICENSE"><img src="https://img.shields.io/github/license/mohaaasan/haircut_project?style=for-the-badge&color=success" alt="License"></a>
</p>

---

## 🌟 ویژگی‌های کلیدی (Features)

- 📅 **رزرو آنلاین نوبت:** امکان انتخاب آرایشگر، خدمات و زمان دلخواه توسط مشتری در چند ثانیه.
- 💇‍♂️ **پروفایل اختصاصی آرایشگران:** نمایش نمونه کارها، تخصص‌ها و امتیازات هر آرایشگر.
- 📱 **طراحی کاملاً واکنش‌گرا (Responsive):** تجربه کاربری عالی در موبایل، تبلت و دسکتاپ.
- 🔔 **سیستم یادآوری:** ارسال نوتیفیکیشن (پیامک/ایمیل) پیش از فرارسیدن زمان نوبت.
- 📊 **پنل مدیریت پیشرفته:** داشبورد جامع برای مدیران جهت بررسی درآمدها، نوبت‌های ثبت‌شده و مدیریت کارمندان.

## 🛠️ تکنولوژی‌های استفاده شده (Tech Stack)

*(این بخش را بر اساس تکنولوژی‌های واقعی پروژه خود ویرایش کنید)*

- **فرانت‌اند:** React.js / Tailwind CSS
- **بک‌اند:** Node.js (Express) / Python (Django)
- **دیتابیس:** MongoDB / PostgreSQL
- **ابزارها:** Git, Docker, Postman

## 🚀 نصب و راه‌اندازی (Installation & Setup)

برای اجرای این پروژه روی سیستم محلی خود، مراحل زیر را دنبال کنید:

1. **کلون کردن مخزن:**
   ```bash
   git clone [https://github.com/mohaaasan/haircut_project.git](https://github.com/mohaaasan/haircut_project.git)
>>>>>>> 0458c0fa2fd55acac77c764e81436ecd5494da20
