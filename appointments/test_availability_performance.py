from datetime import time, timedelta

from django.test import TestCase
from django.utils import timezone

from appointments.models import Appointment, Barber, BarberWorkingSchedule, BlockedTime, BotUser
from appointments.services.availability import get_available_dates, get_available_slots


class AvailabilityBatchTests(TestCase):
    def test_month_uses_three_queries_and_matches_individual_days(self):
        barber = Barber.objects.create(first_name='رضا', last_name='احمدی')
        customer = BotUser.objects.create(bale_user_id=234)
        for weekday in range(1, 8):
            BarberWorkingSchedule.objects.create(barber=barber, day_of_week=weekday, start_time=time(9), end_time=time(11), break_start_time=time(10), break_end_time=time(10, 30))
        start = timezone.localdate() + timedelta(days=1)
        BlockedTime.objects.create(date=start, is_full_day=True)
        BlockedTime.objects.create(barber=barber, date=start + timedelta(days=1), start_time=time(9), end_time=time(9, 45))
        Appointment.objects.create(user=customer, barber=barber, date=start + timedelta(days=1), start_time=time(10, 30), end_time=time(11))
        with self.assertNumQueries(3):
            batched = get_available_dates(barber, start_date=start, days_ahead=30)
        expected = [start + timedelta(days=i) for i in range(30) if get_available_slots(barber, start + timedelta(days=i))]
        self.assertEqual(batched, expected)
        self.assertNotIn(start, batched)
        self.assertNotIn(start + timedelta(days=1), batched)
