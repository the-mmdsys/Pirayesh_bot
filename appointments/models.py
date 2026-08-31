from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from appointments.utils.time_utils import is_appointment_time_in_past


class BotUser(models.Model):
    bale_user_id = models.BigIntegerField(unique=True, db_index=True, verbose_name='شناسه کاربر بله')
    first_name = models.CharField(max_length=100, blank=True, verbose_name='نام')
    last_name = models.CharField(max_length=100, blank=True, verbose_name='نام خانوادگی')
    phone = models.CharField(max_length=20, blank=True, verbose_name='شماره موبایل')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='زمان ایجاد')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='زمان ویرایش')

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'کاربر ربات'
        verbose_name_plural = 'کاربران ربات'

    def __str__(self):
        full_name = f'{self.first_name} {self.last_name}'.strip()
        return full_name or str(self.bale_user_id)


class BotConversationState(models.Model):
    class State(models.TextChoices):
        IDLE = 'idle', 'Idle'
        WAITING_FOR_FIRST_NAME = 'waiting_for_first_name', 'Waiting for first name'
        WAITING_FOR_LAST_NAME = 'waiting_for_last_name', 'Waiting for last name'
        WAITING_FOR_PHONE = 'waiting_for_phone', 'Waiting for phone'
        WAITING_FOR_BARBER = 'waiting_for_barber', 'Waiting for barber'
        WAITING_FOR_DATE = 'waiting_for_date', 'Waiting for date'
        WAITING_FOR_TIME = 'waiting_for_time', 'Waiting for time'
        WAITING_FOR_CONFIRMATION = 'waiting_for_confirmation', 'Waiting for confirmation'
        WAITING_FOR_CANCEL_APPOINTMENT = 'waiting_for_cancel_appointment', 'Waiting for cancel appointment'
        WAITING_FOR_CANCEL_CONFIRMATION = 'waiting_for_cancel_confirmation', 'Waiting for cancel confirmation'

    user = models.OneToOneField(
        BotUser,
        on_delete=models.CASCADE,
        related_name='conversation_state',
        verbose_name='کاربر',
    )
    state = models.CharField(
        max_length=50,
        choices=State.choices,
        default=State.IDLE,
        verbose_name='وضعیت گفتگو',
    )
    data = models.JSONField(default=dict, blank=True, verbose_name='داده موقت')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='زمان ویرایش')

    class Meta:
        verbose_name = 'وضعیت گفتگوی ربات'
        verbose_name_plural = 'وضعیت گفتگوهای ربات'

    def __str__(self):
        return f'{self.user} - {self.state}'

    def reset(self):
        self.state = self.State.IDLE
        self.data = {}
        self.save(update_fields=['state', 'data', 'updated_at'])


class Barber(models.Model):
    first_name = models.CharField(max_length=100, verbose_name='نام')
    last_name = models.CharField(max_length=100, verbose_name='نام خانوادگی')
    description = models.TextField(blank=True, verbose_name='توضیح کوتاه')
    image = models.FileField(upload_to='barbers/', blank=True, null=True, verbose_name='تصویر')
    is_active = models.BooleanField(default=True, verbose_name='فعال است؟')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='زمان ایجاد')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='زمان ویرایش')

    class Meta:
        ordering = ['first_name', 'last_name']
        verbose_name = 'آرایشگر'
        verbose_name_plural = 'آرایشگرها'

    def __str__(self):
        return f'{self.first_name} {self.last_name}'.strip()


class BarberWorkingSchedule(models.Model):
    class Weekday(models.IntegerChoices):
        MONDAY = 1, 'دوشنبه'
        TUESDAY = 2, 'سه شنبه'
        WEDNESDAY = 3, 'چهارشنبه'
        THURSDAY = 4, 'پنجشنبه'
        FRIDAY = 5, 'جمعه'
        SATURDAY = 6, 'شنبه'
        SUNDAY = 7, 'یکشنبه'

    barber = models.ForeignKey(
        Barber,
        on_delete=models.CASCADE,
        related_name='working_schedules',
        verbose_name='آرایشگر',
    )
    day_of_week = models.PositiveSmallIntegerField(choices=Weekday.choices, verbose_name='روز هفته')
    start_time = models.TimeField(verbose_name='ساعت شروع')
    end_time = models.TimeField(verbose_name='ساعت پایان')
    slot_duration_minutes = models.PositiveSmallIntegerField(
        default=30,
        validators=[MinValueValidator(1)],
        verbose_name='مدت هر نوبت به دقیقه',
    )
    break_start_time = models.TimeField(blank=True, null=True, verbose_name='شروع استراحت')
    break_end_time = models.TimeField(blank=True, null=True, verbose_name='پایان استراحت')
    is_active = models.BooleanField(default=True, verbose_name='فعال است؟')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='زمان ایجاد')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='زمان ویرایش')

    class Meta:
        ordering = ['barber', 'day_of_week', 'start_time']
        constraints = [
            models.UniqueConstraint(
                fields=['barber', 'day_of_week'],
                name='unique_barber_schedule_per_weekday',
            ),
            models.CheckConstraint(
                condition=Q(start_time__lt=F('end_time')),
                name='schedule_start_before_end',
            ),
            models.CheckConstraint(
                condition=(
                    Q(break_start_time__isnull=True, break_end_time__isnull=True)
                    | Q(break_start_time__lt=F('break_end_time'))
                ),
                name='schedule_break_start_before_end',
            ),
        ]
        verbose_name = 'برنامه کاری آرایشگر'
        verbose_name_plural = 'برنامه کاری آرایشگرها'

    def __str__(self):
        return f'{self.barber} - {self.get_day_of_week_display()}'

    def clean(self):
        errors = {}

        if self.start_time and self.end_time and self.start_time >= self.end_time:
            errors['end_time'] = 'End time must be after start time.'

        has_break_start = self.break_start_time is not None
        has_break_end = self.break_end_time is not None
        if has_break_start != has_break_end:
            errors['break_end_time'] = 'Set both break start and break end, or leave both empty.'

        if has_break_start and has_break_end:
            if self.break_start_time >= self.break_end_time:
                errors['break_end_time'] = 'Break end time must be after break start time.'
            if self.start_time and self.end_time:
                if self.break_start_time < self.start_time or self.break_end_time > self.end_time:
                    errors['break_start_time'] = 'Break time must be inside working hours.'

        if errors:
            raise ValidationError(errors)


class Appointment(models.Model):
    class Status(models.TextChoices):
        BOOKED = 'booked', 'رزرو شده'
        CANCELLED_BY_USER = 'cancelled_by_user', 'لغو شده توسط کاربر'
        CANCELLED_BY_ADMIN = 'cancelled_by_admin', 'لغو شده توسط ادمین'
        COMPLETED = 'completed', 'انجام شده'
        NO_SHOW = 'no_show', 'عدم مراجعه'

    user = models.ForeignKey(
        BotUser,
        on_delete=models.PROTECT,
        related_name='appointments',
        verbose_name='کاربر',
    )
    barber = models.ForeignKey(
        Barber,
        on_delete=models.PROTECT,
        related_name='appointments',
        verbose_name='آرایشگر',
    )
    date = models.DateField(verbose_name='تاریخ')
    start_time = models.TimeField(verbose_name='ساعت شروع')
    end_time = models.TimeField(blank=True, null=True, verbose_name='ساعت پایان')
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.BOOKED,
        verbose_name='وضعیت',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='زمان ایجاد')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='زمان ویرایش')
    cancelled_at = models.DateTimeField(blank=True, null=True, verbose_name='زمان لغو')

    class Meta:
        ordering = ['date', 'start_time']
        constraints = [
            models.UniqueConstraint(
                fields=['barber', 'date', 'start_time'],
                condition=Q(status='booked'),
                name='unique_booked_appointment_slot',
            ),
        ]
        indexes = [
            models.Index(fields=['date', 'status']),
            models.Index(fields=['barber', 'date']),
            models.Index(fields=['user', 'date']),
        ]
        verbose_name = 'نوبت'
        verbose_name_plural = 'نوبت ها'

    def save(self, *args, **kwargs):
        if self.status in {
            self.Status.CANCELLED_BY_USER,
            self.Status.CANCELLED_BY_ADMIN,
        } and self.cancelled_at is None:
            self.cancelled_at = timezone.now()
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.barber} - {self.date} {self.start_time}'

    def clean(self):
        if self._keeps_original_datetime():
            return

        if is_appointment_time_in_past(self.date, self.start_time):
            today = timezone.localdate()
            if self.date and self.date < today:
                raise ValidationError({'date': 'امکان ثبت نوبت برای تاریخ گذشته وجود ندارد.'})
            raise ValidationError({'start_time': 'امکان ثبت نوبت برای ساعت گذشته امروز وجود ندارد.'})

    def _keeps_original_datetime(self):
        if not self.pk:
            return False

        original = Appointment.objects.filter(pk=self.pk).only('date', 'start_time').first()
        if original is None:
            return False

        return original.date == self.date and original.start_time == self.start_time


class BlockedTime(models.Model):
    barber = models.ForeignKey(
        Barber,
        on_delete=models.CASCADE,
        related_name='blocked_times',
        blank=True,
        null=True,
        verbose_name='آرایشگر',
        help_text='اگر خالی باشد، زمان برای کل آرایشگاه بسته می شود.',
    )
    date = models.DateField(verbose_name='تاریخ')
    is_full_day = models.BooleanField(default=False, verbose_name='کل روز بسته است؟')
    start_time = models.TimeField(blank=True, null=True, verbose_name='ساعت شروع')
    end_time = models.TimeField(blank=True, null=True, verbose_name='ساعت پایان')
    reason = models.CharField(max_length=255, blank=True, verbose_name='دلیل')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='زمان ایجاد')

    class Meta:
        ordering = ['date', 'start_time']
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(is_full_day=True)
                    | Q(start_time__isnull=False, end_time__isnull=False, start_time__lt=F('end_time'))
                ),
                name='blocked_time_valid_range',
            ),
        ]
        verbose_name = 'زمان مسدود شده'
        verbose_name_plural = 'زمان های مسدود شده'

    def __str__(self):
        target = self.barber or 'کل آرایشگاه'
        if self.is_full_day:
            return f'{target} - {self.date} - کل روز'
        return f'{target} - {self.date} {self.start_time}-{self.end_time}'

    def clean(self):
        if self.is_full_day:
            return

        errors = {}
        if self.start_time is None:
            errors['start_time'] = 'Start time is required when this is not a full-day block.'
        if self.end_time is None:
            errors['end_time'] = 'End time is required when this is not a full-day block.'
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            errors['end_time'] = 'End time must be after start time.'

        if errors:
            raise ValidationError(errors)


class SalonSettings(models.Model):
    salon_name = models.CharField(max_length=150, verbose_name='نام آرایشگاه')
    phone = models.CharField(max_length=30, blank=True, verbose_name='شماره تماس')
    address = models.TextField(blank=True, verbose_name='آدرس')
    working_hours_text = models.TextField(blank=True, verbose_name='ساعات کاری')
    location_url = models.URLField(blank=True, verbose_name='لینک لوکیشن')
    reservation_days_ahead = models.PositiveSmallIntegerField(
        default=30,
        validators=[MinValueValidator(1)],
        verbose_name='تعداد روزهای قابل رزرو آینده',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='زمان ایجاد')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='زمان ویرایش')

    class Meta:
        verbose_name = 'تنظیمات آرایشگاه'
        verbose_name_plural = 'تنظیمات آرایشگاه'

    def __str__(self):
        return self.salon_name
