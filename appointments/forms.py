from django import forms

from appointments.models import Appointment, BlockedTime
from appointments.utils.date_utils import gregorian_to_jalali, jalali_to_gregorian


class JalaliDateFormField(forms.CharField):
    default_error_messages = {
        'required': 'لطفا تاریخ شمسی را وارد کنید.',
    }

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('help_text', 'نمونه: 1405/06/08')
        kwargs.setdefault(
            'widget',
            forms.TextInput(
                attrs={
                    'placeholder': '1405/06/08',
                    'dir': 'ltr',
                    'style': 'text-align: left;',
                }
            ),
        )
        super().__init__(*args, **kwargs)

    def prepare_value(self, value):
        if hasattr(value, 'year') and hasattr(value, 'month') and hasattr(value, 'day'):
            return gregorian_to_jalali(value)
        return value

    def to_python(self, value):
        value = super().to_python(value)
        if value in self.empty_values:
            return None
        return jalali_to_gregorian(value)


class AppointmentAdminForm(forms.ModelForm):
    date = JalaliDateFormField(label='تاریخ شمسی')

    class Meta:
        model = Appointment
        fields = '__all__'


class BlockedTimeAdminForm(forms.ModelForm):
    date = JalaliDateFormField(label='تاریخ شمسی')

    class Meta:
        model = BlockedTime
        fields = '__all__'
