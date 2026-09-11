from django import forms
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction

from appointments.forms import JalaliDateFormField
from appointments.models import (
    Appointment,
    Barber,
    BarberPortfolio,
    BarberWorkingSchedule,
    BlockedTime,
    BotUser,
    SalonSettings,
)
from .widgets import PersianTimeField
from .models import BotControl


INPUT_CLASSES = (
    'w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 '
    'outline-none transition focus:border-teal-600 focus:ring-2 focus:ring-teal-100'
)
CHECKBOX_CLASSES = 'h-4 w-4 rounded border-slate-300 text-teal-700 focus:ring-teal-600'


class PanelFormStyleMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in list(self.fields.items()):
            if isinstance(field, forms.TimeField):
                field = PersianTimeField(label=field.label, required=field.required, initial=field.initial)
                self.fields[name] = field
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault('class', CHECKBOX_CLASSES)
                continue
            widget.attrs.setdefault('class', INPUT_CLASSES)
            if isinstance(field, forms.ImageField):
                widget.attrs.setdefault('accept', 'image/jpeg,image/png,image/webp')
                field.help_text = 'تصویر JPG، PNG یا WebP؛ حداکثر ۵ مگابایت.'
                field.validators.append(validate_uploaded_image)


def validate_uploaded_image(value):
    if value.size > 5 * 1024 * 1024:
        raise ValidationError('حجم تصویر باید کمتر از ۵ مگابایت باشد.')
    image = getattr(value, 'image', None)
    if image and (image.format not in {'JPEG', 'PNG', 'WEBP'} or image.width * image.height > 20_000_000):
        raise ValidationError('تصویر JPG، PNG یا WebP با حداکثر ۲۰ میلیون پیکسل انتخاب کنید.')


class PanelModelForm(PanelFormStyleMixin, forms.ModelForm):
    pass


class PanelAuthenticationForm(PanelFormStyleMixin, AuthenticationForm):
    error_messages = {
        'invalid_login': 'نام کاربری یا رمز عبور درست نیست.',
        'inactive': 'این حساب اجازه ورود به پنل مدیریت را ندارد.',
    }

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_staff:
            raise ValidationError(self.error_messages['inactive'], code='inactive')


class AppointmentPanelForm(PanelModelForm):
    date = JalaliDateFormField(label='تاریخ شمسی')

    class Meta:
        model = Appointment
        fields = ['user', 'barber', 'date', 'start_time', 'end_time', 'status']
        labels = {
            'user': 'مشتری',
            'barber': 'آرایشگر',
            'start_time': 'ساعت شروع',
            'end_time': 'ساعت پایان',
            'status': 'وضعیت',
        }
        widgets = {
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user'].queryset = BotUser.objects.order_by('first_name', 'last_name', 'phone')
        self.fields['barber'].queryset = Barber.objects.order_by('first_name', 'last_name')


class BarberPanelForm(PanelModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['experience_years'].required = False

    def clean_experience_years(self):
        return self.cleaned_data.get('experience_years') or 0

    class Meta:
        model = Barber
        fields = ['first_name', 'last_name', 'specialty', 'experience_years', 'description', 'biography', 'image', 'is_active']
        widgets = {'description': forms.Textarea(attrs={'rows': 3}), 'biography': forms.Textarea(attrs={'rows': 5})}
        labels = {
            'first_name': 'نام',
            'last_name': 'نام خانوادگی',
            'description': 'توضیح کوتاه',
            'image': 'تصویر',
            'is_active': 'فعال است؟',
        }


class BarberWorkingSchedulePanelForm(PanelModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'day_of_week' in self.fields:
            self.fields['day_of_week'].choices = WEEKDAY_CHOICES

    class Meta:
        model = BarberWorkingSchedule
        fields = [
            'barber',
            'day_of_week',
            'start_time',
            'end_time',
            'slot_duration_minutes',
            'break_start_time',
            'break_end_time',
            'is_active',
        ]
        labels = {
            'barber': 'آرایشگر',
            'day_of_week': 'روز هفته',
            'start_time': 'ساعت شروع',
            'end_time': 'ساعت پایان',
            'slot_duration_minutes': 'مدت هر نوبت به دقیقه',
            'break_start_time': 'شروع استراحت',
            'break_end_time': 'پایان استراحت',
            'is_active': 'فعال است؟',
        }
        widgets = {
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
            'break_start_time': forms.TimeInput(attrs={'type': 'time'}),
            'break_end_time': forms.TimeInput(attrs={'type': 'time'}),
        }

    def clean_description(self):
        value = self.cleaned_data['description']
        if len(value) > 700:
            raise ValidationError('معرفی کوتاه را در حداکثر ۷۰۰ نویسه بنویسید؛ سوابق بیشتر را در بخش معرفی و سوابق وارد کنید.')
        return value


class BarberPortfolioForm(PanelModelForm):
    class Meta:
        model = BarberPortfolio
        fields = ['image', 'title', 'caption', 'position', 'is_active']
        widgets = {'caption': forms.Textarea(attrs={'rows': 3})}


WEEKDAY_CHOICES = [
    (day, BarberWorkingSchedule.Weekday(day).label)
    for day in (6, 7, 1, 2, 3, 4, 5)
]


class ScheduleCreateForm(BarberWorkingSchedulePanelForm):
    days = forms.ChoiceField(
        label='روزهای کاری',
        choices=[('all', 'هر روز (تمام روزهای هفته)'), *WEEKDAY_CHOICES],
        initial='all',
        help_text=(
            '«هر روز» ساعت یکسانی برای هفت روز ثبت می‌کند و برنامه قبلی این آرایشگر را '
            'به‌روزرسانی می‌کند. برای ساعت متفاوت، یک روز را انتخاب کنید یا برنامه آن روز را ویرایش کنید.'
        ),
    )

    class Meta(BarberWorkingSchedulePanelForm.Meta):
        fields = ['barber', 'days', 'start_time', 'end_time', 'slot_duration_minutes',
                  'break_start_time', 'break_end_time', 'is_active']

    def clean(self):
        data = super().clean()
        barber, days = data.get('barber'), data.get('days')
        if barber and days and days != 'all':
            if BarberWorkingSchedule.objects.filter(barber=barber, day_of_week=int(days)).exists():
                self.add_error('days', 'برای این روز قبلاً برنامه ثبت شده است. از گزینه ویرایش همان روز استفاده کنید.')
        return data

    def save(self):
        if not self.is_valid():
            raise ValueError('Cannot save an invalid schedule form.')
        days = [day for day, _ in WEEKDAY_CHOICES] if self.cleaned_data['days'] == 'all' else [int(self.cleaned_data['days'])]
        values = {
            name: self.cleaned_data[name]
            for name in self.Meta.fields if name not in {'days', 'barber'}
        }
        with transaction.atomic():
            barber = Barber.objects.select_for_update().get(pk=self.cleaned_data['barber'].pk)
            schedules = []
            for day in days:
                schedule = None
                if self.cleaned_data['days'] == 'all':
                    schedule = BarberWorkingSchedule.objects.filter(barber=barber, day_of_week=day).first()
                schedule = schedule or BarberWorkingSchedule(barber=barber, day_of_week=day)
                for name, value in values.items():
                    setattr(schedule, name, value)
                schedule.full_clean()
                schedules.append(schedule)
            for schedule in schedules:
                schedule.save()
        return schedules


class BlockedTimePanelForm(PanelModelForm):
    date = JalaliDateFormField(label='تاریخ شمسی')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        full_day = self.fields['is_full_day'].widget.value_from_datadict(
            self.data, self.files, self.add_prefix('is_full_day'),
        )
        if self.is_bound and full_day:
            for name in ('start_time', 'end_time'):
                self.fields[name].disabled = True
                self.initial[name] = None

    class Meta:
        model = BlockedTime
        fields = ['barber', 'date', 'is_full_day', 'start_time', 'end_time', 'reason']
        labels = {
            'barber': 'آرایشگر',
            'is_full_day': 'کل روز بسته است؟',
            'start_time': 'ساعت شروع',
            'end_time': 'ساعت پایان',
            'reason': 'دلیل',
        }
        widgets = {
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
        }


class SalonSettingsPanelForm(PanelModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['logo'].help_text += ' اگر لوگویی انتخاب نکنید، لوگوی نوشتاری پاییزان نمایش داده می‌شود.'

    class Meta:
        model = SalonSettings
        fields = ['salon_name', 'logo', 'contact_intro', 'phone', 'address', 'working_hours_text', 'location_url', 'social_url', 'reservation_days_ahead']
        widgets = {name: forms.Textarea(attrs={'rows': 3}) for name in ('contact_intro', 'address', 'working_hours_text')}
        labels = {
            'salon_name': 'نام آرایشگاه',
            'phone': 'شماره تماس',
            'address': 'آدرس',
            'working_hours_text': 'ساعات کاری',
            'location_url': 'لینک لوکیشن',
            'reservation_days_ahead': 'تعداد روزهای قابل رزرو آینده',
        }

    def clean(self):
        data = super().clean()
        if sum(len(str(data.get(name) or '')) for name in ('salon_name', 'contact_intro', 'phone', 'address', 'working_hours_text', 'location_url', 'social_url')) > 3500:
            raise ValidationError('برای نمایش کامل در کپشن لوگو، مجموع متن اطلاعات تماس را به کمتر از ۳۵۰۰ نویسه برسانید.')
        return data


class ResetEmailForm(PanelFormStyleMixin, forms.Form):
    email = forms.EmailField(label='ایمیل حساب مدیر اصلی', max_length=254, widget=forms.EmailInput(attrs={'autocomplete': 'email', 'dir': 'ltr'}))


class ResetCodeForm(PanelFormStyleMixin, forms.Form):
    code = forms.CharField(label='کد تأیید شش‌رقمی', max_length=6, min_length=6, widget=forms.TextInput(attrs={'autocomplete': 'one-time-code', 'inputmode': 'numeric', 'dir': 'ltr'}))

    def clean_code(self):
        value = self.cleaned_data['code'].translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789'))
        if not value.isascii() or not value.isdigit():
            raise ValidationError('کد شش‌رقمی داخل ایمیل را وارد کنید.')
        return value


class PanelSetPasswordForm(PanelFormStyleMixin, SetPasswordForm):
    pass


class BotControlForm(PanelModelForm):
    class Meta:
        model = BotControl
        fields = ['offline_message']
        widgets = {'offline_message': forms.Textarea(attrs={'rows': 3})}


class RecoveryEmailForm(PanelFormStyleMixin, forms.Form):
    email = forms.EmailField(label='ایمیل بازیابی رمز', max_length=254, widget=forms.EmailInput(attrs={'autocomplete': 'email', 'dir': 'ltr'}))
    current_password = forms.CharField(label='رمز عبور فعلی', widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}))

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_current_password(self):
        value = self.cleaned_data['current_password']
        if not self.user.check_password(value):
            raise ValidationError('رمز عبور فعلی درست نیست.')
        return value

    def clean_email(self):
        value = self.cleaned_data['email'].strip()
        if get_user_model().objects.filter(email__iexact=value, is_superuser=True).exclude(pk=self.user.pk).exists():
            raise ValidationError('این ایمیل برای یک مدیر اصلی دیگر ثبت شده است.')
        return value
