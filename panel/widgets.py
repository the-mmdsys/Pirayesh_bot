from django import forms

from appointments.utils.date_utils import normalize_date_digits


class ClockTimeInput(forms.TimeInput):
    """A 24-hour text input with an accessible, local alarm-style picker."""

    input_type = 'text'
    template_name = 'panel/widgets/clock_time.html'

    def __init__(self, attrs=None):
        defaults = {'dir': 'ltr', 'placeholder': '09:00', 'autocomplete': 'off'}
        defaults.update(attrs or {})
        super().__init__(attrs=defaults, format='%H:%M')

    class Media:
        css = {'all': ['panel/time-picker.css']}
        js = ['panel/time-picker.js']


class PersianTimeField(forms.TimeField):
    widget = ClockTimeInput
    default_error_messages = {
        'required': 'لطفاً ساعت را انتخاب یا وارد کنید.',
        'invalid': 'ساعت معتبر نیست. از قالب ۲۴ساعته استفاده کنید؛ مانند 09:30 یا 18:00.',
    }

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('input_formats', ['%H:%M', '%H:%M:%S'])
        kwargs.setdefault('help_text', 'قالب ۲۴ساعته؛ برای ساعت ۶ عصر، 18:00 را انتخاب کنید.')
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        if isinstance(value, str):
            value = normalize_date_digits(value.strip())
            value = value.translate(dict.fromkeys(map(ord, '\u200e\u200f\u061c\u202a\u202b\u202c\u2066\u2067\u2068\u2069')))
        return super().to_python(value)
