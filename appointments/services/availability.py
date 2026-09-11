from collections import defaultdict
from datetime import datetime, timedelta

from django.db.models import Q
from django.utils import timezone

from appointments.models import Appointment, BarberWorkingSchedule, BlockedTime, SalonSettings
from appointments.utils.time_utils import appointment_end_datetime


def get_reservation_days_ahead():
    settings = SalonSettings.objects.order_by('id').first()
    if settings:
        return settings.reservation_days_ahead
    return 30


def get_available_dates(barber, start_date=None, days_ahead=None):
    if not barber.is_active:
        return []

    start_date = start_date or timezone.localdate()
    days_ahead = get_reservation_days_ahead() if days_ahead is None else days_ahead
    if days_ahead <= 0:
        return []
    end_date = start_date + timedelta(days=days_ahead - 1)
    schedules = {item.day_of_week: item for item in BarberWorkingSchedule.objects.filter(barber=barber, is_active=True)}
    blocks_by_date = defaultdict(list)
    for block in BlockedTime.objects.filter(date__range=(start_date, end_date)).filter(Q(barber=barber) | Q(barber__isnull=True)):
        blocks_by_date[block.date].append(block)
    appointments_by_date = defaultdict(list)
    for appointment in Appointment.objects.filter(barber=barber, date__range=(start_date, end_date), status=Appointment.Status.BOOKED).only('date', 'start_time', 'end_time'):
        appointments_by_date[appointment.date].append(appointment)
    dates = []

    for day_offset in range(days_ahead):
        current_date = start_date + timedelta(days=day_offset)
        if _available_slots(current_date, schedules.get(current_date.isoweekday()), blocks_by_date[current_date], appointments_by_date[current_date]):
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

    return _available_slots(date, schedule, _get_blocked_times(barber, date), Appointment.objects.filter(
        barber=barber, date=date, status=Appointment.Status.BOOKED,
    ).only('start_time', 'end_time'))


def _available_slots(date, schedule, blocked_times, appointments):
    today = timezone.localdate()
    if not schedule or date < today:
        return []
    slots = _build_slots(schedule, date)
    if not slots:
        return []

    if _has_full_day_block(blocked_times):
        return []

    booked_ranges = [
        (
            datetime.combine(date, appointment.start_time),
            appointment_end_datetime(date, appointment.start_time, appointment.end_time, schedule.slot_duration_minutes),
        )
        for appointment in appointments
    ]

    available_slots = []
    current_time = timezone.localtime().time() if date == today else None
    for slot in slots:
        if current_time and slot['start_time'] <= current_time:
            continue
        if any(
            datetime.combine(date, slot['start_time']) < end
            and datetime.combine(date, slot['end_time']) > start
            for start, end in booked_ranges
        ):
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
    if schedule.slot_duration_minutes <= 0:
        return slots
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
