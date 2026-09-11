from datetime import datetime, timedelta

from django.utils import timezone


def appointment_end_datetime(date, start_time, end_time=None, duration_minutes=30):
    if end_time is not None:
        return datetime.combine(date, end_time)
    return datetime.combine(date, start_time) + timedelta(minutes=max(duration_minutes, 1))


def is_appointment_time_in_past(date, start_time):
    if date is None or start_time is None:
        return False

    appointment_datetime = datetime.combine(date, start_time)
    appointment_datetime = timezone.make_aware(appointment_datetime, timezone.get_current_timezone())
    return appointment_datetime < timezone.localtime()
