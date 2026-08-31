from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from appointments.models import (
    Appointment,
    Barber,
    BarberWorkingSchedule,
    BlockedTime,
    BotUser,
    SalonSettings,
)
from appointments.utils.date_utils import gregorian_to_jalali
from .forms import (
    AppointmentPanelForm,
    BarberPanelForm,
    BarberWorkingSchedulePanelForm,
    BlockedTimePanelForm,
    SalonSettingsPanelForm,
)


@staff_member_required
def dashboard(request):
    today = timezone.localdate()
    current_time = timezone.localtime().time()
    today_appointments = appointments_base_queryset().filter(date=today)
    upcoming_appointments = appointments_base_queryset().filter(
        Q(date__gt=today) | Q(date=today, start_time__gte=current_time)
    )

    context = {
        'title': 'داشبورد',
        'stats': [
            {'label': 'نوبت‌های امروز', 'value': today_appointments.count(), 'accent': 'border-teal-600'},
            {'label': 'نوبت‌های آینده', 'value': upcoming_appointments.count(), 'accent': 'border-amber-500'},
            {'label': 'آرایشگرهای فعال', 'value': Barber.objects.filter(is_active=True).count(), 'accent': 'border-rose-500'},
            {'label': 'کاربران ربات', 'value': BotUser.objects.count(), 'accent': 'border-sky-600'},
        ],
        'today_appointments': today_appointments[:8],
        'upcoming_appointments': upcoming_appointments[:8],
    }
    return render(request, 'panel/dashboard.html', context)


@staff_member_required
def today_appointments(request):
    appointments = appointments_base_queryset().filter(date=timezone.localdate())
    context = {
        'title': 'نوبت‌های امروز',
        'appointments': appointments,
    }
    return render(request, 'panel/appointments/today.html', context)


@staff_member_required
def appointments_list(request):
    appointments = appointments_base_queryset()
    status = request.GET.get('status', '').strip()
    barber_id = request.GET.get('barber', '').strip()
    query = request.GET.get('q', '').strip()

    if status:
        appointments = appointments.filter(status=status)
    if barber_id:
        appointments = appointments.filter(barber_id=barber_id)
    if query:
        appointments = appointments.filter(
            Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(user__phone__icontains=query)
            | Q(barber__first_name__icontains=query)
            | Q(barber__last_name__icontains=query)
        )

    context = {
        'title': 'همه نوبت‌ها',
        'appointments': appointments,
        'barbers': Barber.objects.order_by('first_name', 'last_name'),
        'status_choices': Appointment.Status.choices,
        'filters': {'q': query, 'status': status, 'barber': barber_id},
    }
    return render(request, 'panel/appointments/list.html', context)


@staff_member_required
def appointment_create(request):
    return save_form_view(
        request=request,
        form_class=AppointmentPanelForm,
        template_name='panel/form.html',
        success_url_name='panel:appointments',
        title='ثبت نوبت دستی',
        success_message='نوبت با موفقیت ثبت شد.',
    )


@staff_member_required
def appointment_edit(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    return save_form_view(
        request=request,
        form_class=AppointmentPanelForm,
        template_name='panel/form.html',
        success_url_name='panel:appointments',
        title='ویرایش نوبت',
        success_message='نوبت با موفقیت ویرایش شد.',
        instance=appointment,
    )


@staff_member_required
def appointment_cancel(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    if request.method == 'POST':
        appointment.status = Appointment.Status.CANCELLED_BY_ADMIN
        appointment.cancelled_at = timezone.now()
        appointment.save()
        messages.success(request, 'نوبت توسط ادمین لغو شد.')
        return redirect('panel:appointments')

    return render(
        request,
        'panel/confirm.html',
        {
            'title': 'لغو نوبت',
            'message': f'آیا از لغو نوبت {appointment} مطمئن هستید؟',
            'cancel_url': 'panel:appointments',
        },
    )


@staff_member_required
def barbers_list(request):
    query = request.GET.get('q', '').strip()
    barbers = Barber.objects.order_by('first_name', 'last_name')
    if query:
        barbers = barbers.filter(Q(first_name__icontains=query) | Q(last_name__icontains=query))

    return render(request, 'panel/barbers/list.html', {'title': 'آرایشگرها', 'barbers': barbers, 'query': query})


@staff_member_required
def barber_create(request):
    return save_form_view(
        request=request,
        form_class=BarberPanelForm,
        template_name='panel/form.html',
        success_url_name='panel:barbers',
        title='افزودن آرایشگر',
        success_message='آرایشگر با موفقیت اضافه شد.',
        has_file=True,
    )


@staff_member_required
def barber_edit(request, pk):
    barber = get_object_or_404(Barber, pk=pk)
    return save_form_view(
        request=request,
        form_class=BarberPanelForm,
        template_name='panel/form.html',
        success_url_name='panel:barbers',
        title='ویرایش آرایشگر',
        success_message='آرایشگر با موفقیت ویرایش شد.',
        instance=barber,
        has_file=True,
    )


@staff_member_required
def barber_toggle(request, pk):
    barber = get_object_or_404(Barber, pk=pk)
    if request.method == 'POST':
        barber.is_active = not barber.is_active
        barber.save(update_fields=['is_active', 'updated_at'])
        messages.success(request, 'وضعیت آرایشگر تغییر کرد.')
    return redirect('panel:barbers')


@staff_member_required
def schedules_list(request):
    schedules = BarberWorkingSchedule.objects.select_related('barber').order_by('barber', 'day_of_week')
    return render(request, 'panel/schedules/list.html', {'title': 'برنامه کاری', 'schedules': schedules})


@staff_member_required
def schedule_create(request):
    return save_form_view(
        request=request,
        form_class=BarberWorkingSchedulePanelForm,
        template_name='panel/form.html',
        success_url_name='panel:schedules',
        title='افزودن برنامه کاری',
        success_message='برنامه کاری با موفقیت ثبت شد.',
    )


@staff_member_required
def schedule_edit(request, pk):
    schedule = get_object_or_404(BarberWorkingSchedule, pk=pk)
    return save_form_view(
        request=request,
        form_class=BarberWorkingSchedulePanelForm,
        template_name='panel/form.html',
        success_url_name='panel:schedules',
        title='ویرایش برنامه کاری',
        success_message='برنامه کاری با موفقیت ویرایش شد.',
        instance=schedule,
    )


@staff_member_required
def schedule_delete(request, pk):
    schedule = get_object_or_404(BarberWorkingSchedule, pk=pk)
    return delete_view(
        request=request,
        obj=schedule,
        title='حذف برنامه کاری',
        message=f'آیا از حذف برنامه کاری {schedule} مطمئن هستید؟',
        success_url_name='panel:schedules',
        success_message='برنامه کاری حذف شد.',
    )


@staff_member_required
def blocked_times_list(request):
    blocked_times = BlockedTime.objects.select_related('barber').order_by('date', 'start_time')
    return render(
        request,
        'panel/blocked_times/list.html',
        {'title': 'زمان‌های مسدودشده', 'blocked_times': blocked_times},
    )


@staff_member_required
def blocked_time_create(request):
    return save_form_view(
        request=request,
        form_class=BlockedTimePanelForm,
        template_name='panel/form.html',
        success_url_name='panel:blocked_times',
        title='افزودن زمان مسدود',
        success_message='زمان مسدود با موفقیت ثبت شد.',
    )


@staff_member_required
def blocked_time_edit(request, pk):
    blocked_time = get_object_or_404(BlockedTime, pk=pk)
    return save_form_view(
        request=request,
        form_class=BlockedTimePanelForm,
        template_name='panel/form.html',
        success_url_name='panel:blocked_times',
        title='ویرایش زمان مسدود',
        success_message='زمان مسدود با موفقیت ویرایش شد.',
        instance=blocked_time,
    )


@staff_member_required
def blocked_time_delete(request, pk):
    blocked_time = get_object_or_404(BlockedTime, pk=pk)
    return delete_view(
        request=request,
        obj=blocked_time,
        title='حذف زمان مسدود',
        message=f'آیا از حذف زمان مسدود {blocked_time} مطمئن هستید؟',
        success_url_name='panel:blocked_times',
        success_message='زمان مسدود حذف شد.',
    )


@staff_member_required
def users_list(request):
    query = request.GET.get('q', '').strip()
    users = BotUser.objects.order_by('-created_at')
    if query:
        filters = (
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(phone__icontains=query)
        )
        if query.isdigit():
            filters |= Q(bale_user_id=int(query))
        users = users.filter(filters)

    return render(request, 'panel/users/list.html', {'title': 'کاربران', 'users': users, 'query': query})


@staff_member_required
def salon_settings(request):
    settings = SalonSettings.objects.order_by('id').first()
    return save_form_view(
        request=request,
        form_class=SalonSettingsPanelForm,
        template_name='panel/form.html',
        success_url_name='panel:salon_settings',
        title='تنظیمات آرایشگاه',
        success_message='تنظیمات آرایشگاه ذخیره شد.',
        instance=settings,
    )


def appointments_base_queryset():
    return Appointment.objects.select_related('user', 'barber').order_by('date', 'start_time')


def save_form_view(
    request,
    form_class,
    template_name,
    success_url_name,
    title,
    success_message,
    instance=None,
    has_file=False,
):
    if request.method == 'POST':
        form_kwargs = {'data': request.POST, 'instance': instance}
        if has_file:
            form_kwargs['files'] = request.FILES
        form = form_class(**form_kwargs)
        if form.is_valid():
            form.save()
            messages.success(request, success_message)
            return redirect(success_url_name)
    else:
        form = form_class(instance=instance)

    return render(request, template_name, {'title': title, 'form': form})


def delete_view(request, obj, title, message, success_url_name, success_message):
    if request.method == 'POST':
        obj.delete()
        messages.success(request, success_message)
        return redirect(success_url_name)

    return render(
        request,
        'panel/confirm.html',
        {
            'title': title,
            'message': message,
            'cancel_url': success_url_name,
        },
    )


def to_jalali(value):
    return gregorian_to_jalali(value)
