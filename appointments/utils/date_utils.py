import re

import jdatetime
from django.core.exceptions import ValidationError


JALALI_DATE_FORMAT_HELP = 'فرمت درست تاریخ شمسی: 1405/06/08'


def gregorian_to_jalali(value):
    if value is None:
        return ''

    jalali_date = jdatetime.date.fromgregorian(date=value)
    return f'{jalali_date.year:04d}/{jalali_date.month:02d}/{jalali_date.day:02d}'


def jalali_to_gregorian(value):
    normalized_value = normalize_date_digits(str(value or '').strip())
    if not re.fullmatch(r'\d{4}/\d{2}/\d{2}', normalized_value):
        raise ValidationError(f'تاریخ شمسی معتبر نیست. {JALALI_DATE_FORMAT_HELP}')

    year, month, day = [int(part) for part in normalized_value.split('/')]
    try:
        return jdatetime.date(year, month, day).togregorian()
    except ValueError as error:
        raise ValidationError(f'تاریخ شمسی معتبر نیست. {JALALI_DATE_FORMAT_HELP}') from error


def normalize_date_digits(value):
    translation = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
    return value.translate(translation)
