from datetime import datetime

from django.utils import timezone


def is_appointment_time_in_past(date, start_time):
    if date is None or start_time is None:
        return False

    appointment_datetime = datetime.combine(date, start_time)
    appointment_datetime = timezone.make_aware(appointment_datetime, timezone.get_current_timezone())
    return appointment_datetime < timezone.localtime()
