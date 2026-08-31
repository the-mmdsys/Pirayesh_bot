from django.contrib import admin
from django.db.models import Q
from django.utils import timezone

from .forms import AppointmentAdminForm, BlockedTimeAdminForm
from .models import (
    Appointment,
    Barber,
    BarberWorkingSchedule,
    BlockedTime,
    BotConversationState,
    BotUser,
    SalonSettings,
)
from .utils.date_utils import gregorian_to_jalali


class AppointmentDateFilter(admin.SimpleListFilter):
    title = 'تاریخ نوبت'
    parameter_name = 'appointment_date'

    def lookups(self, request, model_admin):
        return [
            ('today', 'امروز'),
            ('upcoming', 'آینده'),
            ('past', 'گذشته'),
        ]

    def queryset(self, request, queryset):
        today = timezone.localdate()
        current_time = timezone.localtime().time()

        if self.value() == 'today':
            return queryset.filter(date=today)

        if self.value() == 'upcoming':
            return queryset.filter(Q(date__gt=today) | Q(date=today, start_time__gte=current_time))

        if self.value() == 'past':
            return queryset.filter(Q(date__lt=today) | Q(date=today, start_time__lt=current_time))

        return queryset


@admin.register(BotUser)
class BotUserAdmin(admin.ModelAdmin):
    list_display = ['bale_user_id', 'first_name', 'last_name', 'phone', 'created_at']
    search_fields = ['bale_user_id', 'first_name', 'last_name', 'phone']
    ordering = ['-created_at']
    list_per_page = 25


@admin.register(BotConversationState)
class BotConversationStateAdmin(admin.ModelAdmin):
    list_display = ['user', 'state', 'updated_at']
    list_filter = ['state']
    search_fields = ['user__bale_user_id', 'user__first_name', 'user__last_name', 'user__phone']
    ordering = ['-updated_at']
    list_select_related = ['user']
    list_per_page = 25


class BarberWorkingScheduleInline(admin.TabularInline):
    model = BarberWorkingSchedule
    extra = 0
    fields = [
        'day_of_week',
        'start_time',
        'end_time',
        'slot_duration_minutes',
        'break_start_time',
        'break_end_time',
        'is_active',
    ]


@admin.register(Barber)
class BarberAdmin(admin.ModelAdmin):
    list_display = ['first_name', 'last_name', 'is_active', 'created_at', 'updated_at']
    list_filter = ['is_active']
    search_fields = ['first_name', 'last_name', 'description']
    ordering = ['first_name', 'last_name']
    inlines = [BarberWorkingScheduleInline]
    list_per_page = 25
    actions = ['activate_barbers', 'deactivate_barbers']

    @admin.action(description='فعال کردن آرایشگرهای انتخاب شده')
    def activate_barbers(self, request, queryset):
        queryset.update(is_active=True)

    @admin.action(description='غیرفعال کردن آرایشگرهای انتخاب شده')
    def deactivate_barbers(self, request, queryset):
        queryset.update(is_active=False)


@admin.register(BarberWorkingSchedule)
class BarberWorkingScheduleAdmin(admin.ModelAdmin):
    list_display = [
        'barber',
        'day_of_week',
        'start_time',
        'end_time',
        'slot_duration_minutes',
        'is_active',
    ]
    list_filter = ['day_of_week', 'is_active', 'barber']
    list_editable = ['start_time', 'end_time', 'slot_duration_minutes', 'is_active']
    search_fields = ['barber__first_name', 'barber__last_name']
    ordering = ['barber', 'day_of_week', 'start_time']
    list_select_related = ['barber']
    list_per_page = 25


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    form = AppointmentAdminForm
    list_display = [
        'id',
        'user',
        'customer_phone',
        'barber',
        'jalali_date',
        'start_time',
        'end_time',
        'status',
        'cancelled_at',
    ]
    list_filter = [AppointmentDateFilter, 'status', 'barber']
    search_fields = [
        '=id',
        'user__first_name',
        'user__last_name',
        'user__phone',
        'user__bale_user_id',
        'barber__first_name',
        'barber__last_name',
    ]
    ordering = ['date', 'start_time']
    list_select_related = ['user', 'barber']
    list_per_page = 50
    readonly_fields = ['created_at', 'updated_at', 'cancelled_at']
    actions = ['mark_booked', 'mark_cancelled_by_admin', 'mark_completed', 'mark_no_show']
    fieldsets = [
        (
            'اطلاعات نوبت',
            {
                'fields': ['user', 'barber', 'date', 'start_time', 'end_time', 'status'],
            },
        ),
        (
            'زمان های سیستمی',
            {
                'fields': ['created_at', 'updated_at', 'cancelled_at'],
                'classes': ['collapse'],
            },
        ),
    ]

    @admin.display(description='تاریخ شمسی', ordering='date')
    def jalali_date(self, obj):
        return gregorian_to_jalali(obj.date)

    @admin.display(description='موبایل مشتری', ordering='user__phone')
    def customer_phone(self, obj):
        return obj.user.phone

    @admin.action(description='برگرداندن به رزرو شده')
    def mark_booked(self, request, queryset):
        queryset.update(status=Appointment.Status.BOOKED, cancelled_at=None)

    @admin.action(description='لغو توسط ادمین')
    def mark_cancelled_by_admin(self, request, queryset):
        queryset.update(status=Appointment.Status.CANCELLED_BY_ADMIN, cancelled_at=timezone.now())

    @admin.action(description='ثبت به عنوان انجام شده')
    def mark_completed(self, request, queryset):
        queryset.update(status=Appointment.Status.COMPLETED)

    @admin.action(description='ثبت به عنوان عدم مراجعه')
    def mark_no_show(self, request, queryset):
        queryset.update(status=Appointment.Status.NO_SHOW)


@admin.register(BlockedTime)
class BlockedTimeAdmin(admin.ModelAdmin):
    form = BlockedTimeAdminForm
    list_display = ['barber', 'jalali_date', 'is_full_day', 'start_time', 'end_time', 'reason']
    list_filter = ['is_full_day', 'barber']
    list_editable = ['is_full_day', 'start_time', 'end_time']
    search_fields = ['barber__first_name', 'barber__last_name', 'reason']
    ordering = ['date', 'start_time']
    list_select_related = ['barber']
    list_per_page = 50

    @admin.display(description='تاریخ شمسی', ordering='date')
    def jalali_date(self, obj):
        return gregorian_to_jalali(obj.date)


@admin.register(SalonSettings)
class SalonSettingsAdmin(admin.ModelAdmin):
    list_display = ['salon_name', 'phone', 'reservation_days_ahead', 'updated_at']
    search_fields = ['salon_name', 'phone', 'address']

    def has_add_permission(self, request):
        if SalonSettings.objects.exists():
            return False
        return super().has_add_permission(request)
