from datetime import datetime

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import F, Q
from django.utils import timezone

from appointments.utils.time_utils import appointment_end_datetime, is_appointment_time_in_past


class BotUser(models.Model):
    bale_user_id = models.BigIntegerField(unique=True, db_index=True, verbose_name='شناسه کاربر بله')
    full_name = models.CharField(max_length=200, blank=True, verbose_name='نام و نام خانوادگی')
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
        return self.full_name or f'{self.first_name} {self.last_name}'.strip() or str(self.bale_user_id)


class BotConversationState(models.Model):
    class State(models.TextChoices):
        IDLE = 'idle', 'Idle'
        WAITING_FOR_FULL_NAME = 'waiting_for_full_name', 'دریافت نام و نام خانوادگی'
        WAITING_FOR_BARBER_PROFILE = 'waiting_for_barber_profile', 'مشاهده پروفایل آرایشگر'
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
    specialty = models.CharField(max_length=160, blank=True, verbose_name='تخصص‌ها')
    experience_years = models.PositiveSmallIntegerField(default=0, verbose_name='سال‌های تجربه')
    biography = models.TextField(blank=True, max_length=2000, verbose_name='معرفی و سوابق')
    image = models.ImageField(upload_to='barbers/', blank=True, null=True, verbose_name='تصویر')
    is_active = models.BooleanField(default=True, verbose_name='فعال است؟')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='زمان ایجاد')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='زمان ویرایش')

    class Meta:
        ordering = ['first_name', 'last_name']
        verbose_name = 'آرایشگر'
        verbose_name_plural = 'آرایشگرها'

    def __str__(self):
        return f'{self.first_name} {self.last_name}'.strip()


class BarberPortfolio(models.Model):
    barber = models.ForeignKey(Barber, on_delete=models.CASCADE, related_name='portfolio', verbose_name='آرایشگر')
    image = models.ImageField(upload_to='barbers/portfolio/', verbose_name='تصویر نمونه‌کار')
    title = models.CharField(max_length=120, blank=True, verbose_name='عنوان نمونه‌کار')
    caption = models.TextField(max_length=1000, blank=True, verbose_name='توضیحات')
    position = models.PositiveSmallIntegerField(default=0, verbose_name='ترتیب نمایش')
    is_active = models.BooleanField(default=True, verbose_name='نمایش در ربات')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['position', 'id']
        verbose_name = 'نمونه‌کار'
        verbose_name_plural = 'نمونه‌کارهای آرایشگران'

    def __str__(self):
        return self.title or f'نمونه‌کار {self.barber}'


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
                violation_error_message='برای این آرایشگر در این روز قبلاً برنامه کاری ثبت شده است.',
            ),
            models.CheckConstraint(
                condition=Q(start_time__lt=F('end_time')),
                name='schedule_start_before_end',
                violation_error_message='ساعت پایان کار باید بعد از ساعت شروع باشد.',
            ),
            models.CheckConstraint(
                condition=(
                    Q(break_start_time__isnull=True, break_end_time__isnull=True)
                    | Q(break_start_time__lt=F('break_end_time'))
                ),
                name='schedule_break_start_before_end',
                violation_error_message='شروع و پایان استراحت را به ترتیب و با هم وارد کنید.',
            ),
        ]
        verbose_name = 'برنامه کاری آرایشگر'
        verbose_name_plural = 'برنامه کاری آرایشگرها'

    def __str__(self):
        return f'{self.barber} - {self.get_day_of_week_display()}'

    def clean(self):
        errors = {}

        if self.start_time and self.end_time and self.start_time >= self.end_time:
            errors['end_time'] = 'ساعت پایان باید بعد از ساعت شروع باشد. ساعت را به صورت ۲۴ساعته وارد کنید.'

        has_break_start = self.break_start_time is not None
        has_break_end = self.break_end_time is not None
        if has_break_start != has_break_end:
            errors['break_end_time'] = 'شروع و پایان استراحت را با هم وارد کنید یا هر دو را خالی بگذارید.'

        if has_break_start and has_break_end:
            if self.break_start_time >= self.break_end_time:
                errors['break_end_time'] = 'ساعت پایان استراحت باید بعد از ساعت شروع استراحت باشد.'
            if self.start_time and self.end_time:
                if self.break_start_time < self.start_time or self.break_end_time > self.end_time:
                    errors['break_start_time'] = 'زمان استراحت باید داخل بازه ساعت کاری باشد.'

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
                violation_error_message='این ساعت برای آرایشگر انتخاب‌شده قبلاً رزرو شده است.',
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
        elif self.status == self.Status.BOOKED:
            self.cancelled_at = None
        if kwargs.get('update_fields') is not None:
            kwargs['update_fields'] = set(kwargs['update_fields']) | {'cancelled_at'}
        with transaction.atomic():
            # Serialize manual and bot bookings against the same barber on databases
            # with row locks. The unique slot constraint also protects exact duplicates.
            if self.barber_id:
                Barber.objects.select_for_update().filter(pk=self.barber_id).first()
            self.full_clean()
            return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.barber} - {self.date} {self.start_time}'

    def clean(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError({'end_time': 'ساعت پایان نوبت باید بعد از ساعت شروع باشد.'})

        if not self._keeps_original_datetime() and is_appointment_time_in_past(self.date, self.start_time):
            today = timezone.localdate()
            if self.date and self.date < today:
                raise ValidationError({'date': 'امکان ثبت نوبت برای تاریخ گذشته وجود ندارد.'})
            raise ValidationError({'start_time': 'امکان ثبت نوبت برای ساعت گذشته امروز وجود ندارد.'})

        if self.status == self.Status.BOOKED and self.barber_id and self.date and self.start_time:
            schedule = BarberWorkingSchedule.objects.filter(
                barber_id=self.barber_id, day_of_week=self.date.isoweekday(),
            ).first()
            duration = schedule.slot_duration_minutes if schedule else 30
            start = datetime.combine(self.date, self.start_time)
            end = appointment_end_datetime(self.date, self.start_time, self.end_time, duration)
            others = Appointment.objects.filter(
                barber_id=self.barber_id, date=self.date, status=self.Status.BOOKED,
            ).exclude(pk=self.pk)
            for other in others:
                other_end = appointment_end_datetime(other.date, other.start_time, other.end_time, duration)
                if start < other_end and end > datetime.combine(other.date, other.start_time):
                    raise ValidationError({'start_time': 'این بازه با نوبت رزروشده دیگری برای این آرایشگر تداخل دارد.'})

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
                violation_error_message='برای بستن بخشی از روز، یک بازه ساعت معتبر وارد کنید.',
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
            self.start_time = None
            self.end_time = None
            return

        errors = {}
        if self.start_time is None:
            errors['start_time'] = 'برای بستن بخشی از روز، ساعت شروع را وارد کنید.'
        if self.end_time is None:
            errors['end_time'] = 'برای بستن بخشی از روز، ساعت پایان را وارد کنید.'
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            errors['end_time'] = 'ساعت پایان باید بعد از ساعت شروع باشد. ساعت را به صورت ۲۴ساعته وارد کنید.'

        if errors:
            raise ValidationError(errors)


class SalonSettings(models.Model):
    salon_name = models.CharField(max_length=150, verbose_name='نام آرایشگاه')
    logo = models.ImageField(upload_to='salon/', blank=True, verbose_name='لوگوی آرایشگاه')
    contact_intro = models.TextField(max_length=1000, blank=True, verbose_name='متن خوشامد ارتباط با ما')
    social_url = models.URLField(blank=True, verbose_name='لینک شبکه اجتماعی')
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
