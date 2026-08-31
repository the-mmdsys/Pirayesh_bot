from django import template
from django.utils import timezone

from appointments.utils.date_utils import gregorian_to_jalali

register = template.Library()


@register.filter
def jalali_date(value):
    return gregorian_to_jalali(value)


@register.filter
def jalali_datetime(value):
    if value is None:
        return ''
    local_value = timezone.localtime(value)
    return f'{gregorian_to_jalali(local_value.date())} {local_value:%H:%M}'


@register.filter
def status_badge_class(status):
    classes = {
        'booked': 'bg-teal-50 text-teal-800 ring-teal-200',
        'cancelled_by_user': 'bg-rose-50 text-rose-800 ring-rose-200',
        'cancelled_by_admin': 'bg-rose-50 text-rose-800 ring-rose-200',
        'completed': 'bg-sky-50 text-sky-800 ring-sky-200',
        'no_show': 'bg-amber-50 text-amber-800 ring-amber-200',
    }
    return classes.get(status, 'bg-slate-100 text-slate-800 ring-slate-200')
