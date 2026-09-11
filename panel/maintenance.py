import os
import subprocess
import sys
from datetime import timedelta

from django.conf import settings
from django.contrib.sessions.models import Session
from django.db import connection
from django.utils import timezone

from .models import MaintenanceJob, PasswordResetChallenge, RateLimitBucket


def package_updates_available():
    return settings.BOT_ALLOW_PACKAGE_UPDATES and sys.prefix != sys.base_prefix


def launch_job(job):
    kwargs = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
    # All arguments originate in application code. No shell or user-supplied commands.
    subprocess.Popen(
        [sys.executable, str(settings.BASE_DIR / 'manage.py'), 'maintain_bot', str(job.pk)],
        cwd=str(settings.BASE_DIR), stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, **kwargs,
    )


def recover_stale_jobs():
    MaintenanceJob.objects.filter(active=True, created_at__lt=timezone.now() - timedelta(minutes=45)).update(
        active=None, status=MaintenanceJob.Status.FAILED, finished_at=timezone.now(),
        summary='عملیات در زمان مجاز تمام نشد. پیش از تلاش دوباره، وضعیت سرویس و گزارش نگهداری را بررسی کنید.',
    )


def run_command(arguments, timeout=120):
    kwargs = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    completed = subprocess.run(
        [sys.executable, *arguments], cwd=str(settings.BASE_DIR), stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
        timeout=timeout, check=False, **kwargs,
    )
    if completed.returncode:
        # Raw subprocess output can contain paths, private index URLs or credentials.
        raise RuntimeError('Maintenance subprocess failed')
    return completed.stdout


def run_job(job_id):
    claimed = MaintenanceJob.objects.filter(pk=job_id, active=True, status=MaintenanceJob.Status.QUEUED).update(
        status=MaintenanceJob.Status.RUNNING, started_at=timezone.now(), summary='در حال بررسی و نگهداری…',
    )
    if not claimed:
        return
    job = MaintenanceJob.objects.get(pk=job_id)
    package_install_started = False
    stage = 'بررسی اولیه'
    try:
        run_command(['manage.py', 'check'])
        stage = 'پاک‌سازی داده‌های موقت'
        now = timezone.now()
        expired_sessions = Session.objects.filter(expire_date__lt=now).count()
        Session.objects.filter(expire_date__lt=now).delete()
        PasswordResetChallenge.objects.filter(expires_at__lt=now).delete()
        RateLimitBucket.objects.filter(expires_at__lt=now).delete()
        if connection.vendor == 'sqlite':
            with connection.cursor() as cursor:
                cursor.execute('PRAGMA optimize')
        elif connection.vendor == 'postgresql':
            with connection.cursor() as cursor:
                cursor.execute('ANALYZE appointments_appointment, appointments_barberworkingschedule, appointments_blockedtime')
        if job.upgrade_packages:
            if not package_updates_available():
                raise RuntimeError('Package updates require an enabled virtual environment')
            stage = 'ذخیره فهرست نسخه‌های قبلی'
            versions = run_command(['-m', 'pip', 'freeze', '--local'])
            report_dir = settings.BASE_DIR / '.maintenance'
            report_dir.mkdir(exist_ok=True)
            (report_dir / f'{job.pk}-before.txt').write_text(versions, encoding='utf-8')
            stage = 'به‌روزرسانی پکیج‌ها'
            package_install_started = True
            MaintenanceJob.objects.filter(pk=job.pk).update(restart_required=True, summary='در حال دریافت و نصب نسخه‌های سازگار پکیج‌ها…')
            run_command([
                '-m', 'pip', '--disable-pip-version-check', 'install', '--upgrade', '--upgrade-strategy',
                'only-if-needed', '--no-input', '--timeout', '30', '--retries', '1',
                '-r', str(settings.BASE_DIR / 'requirement.txt'),
            ], timeout=600)
            stage = 'بررسی سازگاری پکیج‌ها'
            run_command(['-m', 'pip', 'check'])
            run_command(['manage.py', 'check'])
            run_command(['manage.py', 'migrate', '--check'])
        summary = f'نگهداری انجام شد؛ {expired_sessions} نشست منقضی پاک شد و پایگاه داده بررسی شد.'
        if job.upgrade_packages:
            summary += ' پکیج‌ها به‌روز و سازگاری آن‌ها بررسی شد. برای استفاده از نسخه‌های جدید، سرویس پنل و ربات را دوباره اجرا کنید.'
        MaintenanceJob.objects.filter(pk=job.pk).update(
            active=None, status=MaintenanceJob.Status.SUCCEEDED, summary=summary,
            restart_required=package_install_started, finished_at=timezone.now(),
        )
    except Exception:
        summary = f'عملیات در مرحله «{stage}» متوقف شد. تنظیمات، دسترسی فایل‌ها و اتصال اینترنت سرور را بررسی کنید.'
        if package_install_started:
            summary += ' ممکن است بخشی از پکیج‌ها تغییر کرده باشند. فهرست نسخه‌های قبلی در پوشه .maintenance ذخیره شده است؛ پیش از راه‌اندازی مجدد، سازگاری پکیج‌ها را بررسی کنید.'
        MaintenanceJob.objects.filter(pk=job.pk).update(
            active=None, status=MaintenanceJob.Status.FAILED, summary=summary,
            restart_required=package_install_started, finished_at=timezone.now(),
        )
