from django import forms

from appointments.forms import JalaliDateFormField
from appointments.models import (
    Appointment,
    Barber,
    BarberWorkingSchedule,
    BlockedTime,
    BotUser,
    SalonSettings,
)


INPUT_CLASSES = (
    'w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 '
    'outline-none transition focus:border-teal-600 focus:ring-2 focus:ring-teal-100'
)
CHECKBOX_CLASSES = 'h-4 w-4 rounded border-slate-300 text-teal-700 focus:ring-teal-600'


class PanelModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault('class', CHECKBOX_CLASSES)
                continue
            widget.attrs.setdefault('class', INPUT_CLASSES)


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
    class Meta:
        model = Barber
        fields = ['first_name', 'last_name', 'description', 'image', 'is_active']
        labels = {
            'first_name': 'نام',
            'last_name': 'نام خانوادگی',
            'description': 'توضیح کوتاه',
            'image': 'تصویر',
            'is_active': 'فعال است؟',
        }


class BarberWorkingSchedulePanelForm(PanelModelForm):
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


class BlockedTimePanelForm(PanelModelForm):
    date = JalaliDateFormField(label='تاریخ شمسی')

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
    class Meta:
        model = SalonSettings
        fields = ['salon_name', 'phone', 'address', 'working_hours_text', 'location_url', 'reservation_days_ahead']
        labels = {
            'salon_name': 'نام آرایشگاه',
            'phone': 'شماره تماس',
            'address': 'آدرس',
            'working_hours_text': 'ساعات کاری',
            'location_url': 'لینک لوکیشن',
            'reservation_days_ahead': 'تعداد روزهای قابل رزرو آینده',
        }
