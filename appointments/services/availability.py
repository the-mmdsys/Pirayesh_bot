from datetime import datetime, timedelta

from django.db.models import Q
from django.utils import timezone

from appointments.models import Appointment, BarberWorkingSchedule, BlockedTime, SalonSettings


def get_reservation_days_ahead():
    settings = SalonSettings.objects.order_by('id').first()
    if settings:
        return settings.reservation_days_ahead
    return 30


def get_available_dates(barber, start_date=None, days_ahead=None):
    if not barber.is_active:
        return []

    start_date = start_date or timezone.localdate()
    days_ahead = days_ahead or get_reservation_days_ahead()
    dates = []

    for day_offset in range(days_ahead):
        current_date = start_date + timedelta(days=day_offset)
        if get_available_slots(barber, current_date):
            dates.append(current_date)

    return dates


def get_available_slots(barber, date):
    today = timezone.localdate()
    if date < today or not barber.is_active:
        return []

    schedule = BarberWorkingSchedule.objects.filter(
        barber=barber,
        day_of_week=date.isoweekday(),
        is_active=True,
    ).first()
    if schedule is None:
        return []

    slots = _build_slots(schedule, date)
    if not slots:
        return []

    blocked_times = _get_blocked_times(barber, date)
    if _has_full_day_block(blocked_times):
        return []

    booked_start_times = set(
        Appointment.objects.filter(
            barber=barber,
            date=date,
            status=Appointment.Status.BOOKED,
        ).values_list('start_time', flat=True)
    )

    available_slots = []
    current_time = timezone.localtime().time() if date == today else None
    for slot in slots:
        if current_time and slot['start_time'] <= current_time:
            continue
        if slot['start_time'] in booked_start_times:
            continue
        if _overlaps_any_block(slot, blocked_times):
            continue
        available_slots.append(slot['start_time'])

    return available_slots


def is_slot_available(barber, date, start_time):
    return start_time in get_available_slots(barber, date)


def get_slot_end_time(barber, date, start_time):
    schedule = BarberWorkingSchedule.objects.filter(
        barber=barber,
        day_of_week=date.isoweekday(),
        is_active=True,
    ).first()
    if schedule is None:
        return None

    start_datetime = datetime.combine(date, start_time)
    end_datetime = start_datetime + timedelta(minutes=schedule.slot_duration_minutes)
    return end_datetime.time()


def _build_slots(schedule, date):
    slots = []
    slot_duration = timedelta(minutes=schedule.slot_duration_minutes)
    current_start = datetime.combine(date, schedule.start_time)
    day_end = datetime.combine(date, schedule.end_time)

    while current_start + slot_duration <= day_end:
        current_end = current_start + slot_duration
        slot = {
            'start_time': current_start.time(),
            'end_time': current_end.time(),
        }
        if not _overlaps_break(slot, schedule, date):
            slots.append(slot)
        current_start += slot_duration

    return slots


def _overlaps_break(slot, schedule, date):
    if not schedule.break_start_time or not schedule.break_end_time:
        return False

    break_start = datetime.combine(date, schedule.break_start_time).time()
    break_end = datetime.combine(date, schedule.break_end_time).time()
    return slot['start_time'] < break_end and slot['end_time'] > break_start


def _get_blocked_times(barber, date):
    return list(
        BlockedTime.objects.filter(date=date).filter(
            Q(barber=barber) | Q(barber__isnull=True)
        )
    )


def _has_full_day_block(blocked_times):
    return any(block.is_full_day for block in blocked_times)


def _overlaps_any_block(slot, blocked_times):
    for blocked_time in blocked_times:
        if blocked_time.is_full_day:
            return True
        if slot['start_time'] < blocked_time.end_time and slot['end_time'] > blocked_time.start_time:
            return True
    return False
