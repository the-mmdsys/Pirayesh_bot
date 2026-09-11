import re

from appointments.utils.date_utils import normalize_date_digits


def positive_id(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    value = normalize_date_digits(str(value).strip())
    if not value.isdecimal() or len(value) > 19:
        return None
    number = int(value)
    return number if 0 < number <= 9223372036854775807 else None


def selection_id(text):
    if not isinstance(text, str):
        return None
    match = re.search(r'#(\d+)\s*$', text)
    return positive_id(match.group(1)) if match else None
