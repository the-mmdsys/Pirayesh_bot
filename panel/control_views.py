from functools import wraps

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .auth import staff_member_required
from .forms import BotControlForm
from .maintenance import launch_job, package_updates_available, recover_stale_jobs
from .models import BotControl, MaintenanceJob


def superuser_required(view):
    @staff_member_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapped


@superuser_required
@never_cache
def bot_control(request):
    control = BotControl.current()
    form = BotControlForm(request.POST if request.method == 'POST' else None, instance=control)
    if request.method == 'POST' and form.is_valid():
        # Save just this field so a concurrent on/off action is not overwritten.
        BotControl.objects.filter(pk=1).update(
            offline_message=form.cleaned_data['offline_message'], updated_by=request.user, updated_at=timezone.now(),
        )
        messages.success(request, 'پیام توقف موقت ربات ذخیره شد.')
        return redirect('panel:bot_control')
    recover_stale_jobs()
    return render(request, 'panel/bot_control.html', {
        'title': 'مدیریت ربات', 'control': control, 'form': form,
        'jobs': MaintenanceJob.objects.select_related('requested_by')[:10],
        'active_job': MaintenanceJob.objects.filter(active=True).first(),
        'can_upgrade': package_updates_available(),
    })


@superuser_required
@require_POST
def bot_toggle(request):
    value = request.POST.get('state')
    if value not in {'on', 'off'}:
        return JsonResponse({'error': 'invalid_state'}, status=400)
    BotControl.current()
    BotControl.objects.filter(pk=1).update(is_enabled=value == 'on', updated_by=request.user, updated_at=timezone.now())
    messages.success(request, 'ربات روشن شد و درخواست‌های تازه را می‌پذیرد.' if value == 'on' else 'ربات موقتاً خاموش شد؛ کاربران پیام توقف را دریافت می‌کنند.')
    return redirect('panel:bot_control')


@superuser_required
@require_POST
def bot_maintain(request):
    action = request.POST.get('action')
    if action not in {'optimize', 'upgrade'}:
        return JsonResponse({'error': 'invalid_action'}, status=400)
    if action == 'upgrade' and not package_updates_available():
        messages.error(request, 'به‌روزرسانی پکیج‌ها در این محیط فعال نیست؛ پروژه را در محیط مجازی اجرا کنید.')
        return redirect('panel:bot_control')
    recover_stale_jobs()
    try:
        with transaction.atomic():
            job = MaintenanceJob.objects.create(requested_by=request.user, upgrade_packages=action == 'upgrade')
    except IntegrityError:
        messages.info(request, 'یک عملیات در حال اجراست. نتیجه آن در همین صفحه نمایش داده می‌شود.')
    else:
        try:
            launch_job(job)
        except OSError:
            MaintenanceJob.objects.filter(pk=job.pk).update(
                active=None, status=MaintenanceJob.Status.FAILED, finished_at=timezone.now(),
                summary='امکان اجرای عملیات روی سرور فراهم نشد. دسترسی اجرای Python را بررسی کنید.',
            )
            messages.error(request, 'اجرای عملیات شروع نشد. جزئیات در تاریخچه ثبت شد.')
        else:
            messages.success(request, 'عملیات شروع شد. نتیجه به‌صورت خودکار در این صفحه نمایش داده می‌شود.')
    return redirect('panel:bot_control')


@superuser_required
@never_cache
def maintenance_status(request):
    recover_stale_jobs()
    job = MaintenanceJob.objects.first()
    return JsonResponse({'active': bool(job and job.active), 'summary': job.summary if job else ''})
