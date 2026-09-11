from datetime import time, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Barber, BarberWorkingSchedule
from appointments.services.availability import get_available_slots
from panel.forms import BarberWorkingSchedulePanelForm, ScheduleCreateForm


class SchedulePanelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(username='schedule_staff', is_staff=True)
        cls.barber = Barber.objects.create(first_name='رضا', last_name='احمدی')

    def setUp(self):
        self.client.force_login(self.staff)
        self.data = {
            'barber': self.barber.pk, 'days': '6', 'start_time': '09:00', 'end_time': '18:00',
            'slot_duration_minutes': '30', 'break_start_time': '', 'break_end_time': '', 'is_active': 'on',
        }

    def create(self, **overrides):
        return self.client.post(reverse('panel:schedule_create'), {**self.data, **overrides})

    def test_one_day_accepts_morning_to_evening_and_stores_24_hour_values(self):
        response = self.create()
        self.assertRedirects(response, reverse('panel:schedules'))
        schedule = BarberWorkingSchedule.objects.get()
        self.assertEqual((schedule.day_of_week, schedule.start_time, schedule.end_time), (6, time(9), time(18)))

    def test_persian_and_arabic_digits_are_accepted(self):
        response = self.create(start_time='۰۹:۳۰', end_time='١٨:٤٥')
        self.assertRedirects(response, reverse('panel:schedules'))
        schedule = BarberWorkingSchedule.objects.get()
        self.assertEqual((schedule.start_time, schedule.end_time), (time(9, 30), time(18, 45)))

    def test_every_day_creates_seven_independent_schedules(self):
        self.assertRedirects(self.create(days='all'), reverse('panel:schedules'))
        schedules = BarberWorkingSchedule.objects.all()
        self.assertEqual(set(schedules.values_list('day_of_week', flat=True)), set(range(1, 8)))
        self.assertTrue(all(item.start_time == time(9) and item.end_time == time(18) for item in schedules))

    def test_every_day_updates_existing_days_and_preserves_their_ids(self):
        self.create()
        original = BarberWorkingSchedule.objects.get()
        self.assertRedirects(self.create(days='all', start_time='10:00'), reverse('panel:schedules'))
        original.refresh_from_db()
        self.assertEqual(original.start_time, time(10))
        self.assertEqual(BarberWorkingSchedule.objects.count(), 7)

    def test_each_day_can_be_edited_without_changing_other_days(self):
        self.create(days='all')
        sunday = BarberWorkingSchedule.objects.get(day_of_week=7)
        response = self.client.post(reverse('panel:schedule_edit', args=[sunday.pk]), {
            **self.data, 'day_of_week': '7', 'start_time': '14:00', 'end_time': '21:00',
        })
        self.assertRedirects(response, reverse('panel:schedules'))
        sunday.refresh_from_db()
        self.assertEqual(sunday.start_time, time(14))
        self.assertEqual(BarberWorkingSchedule.objects.filter(start_time=time(9)).count(), 6)

    def test_duplicate_single_day_has_persian_error(self):
        self.create()
        response = self.create()
        self.assertContains(response, 'برای این روز قبلاً برنامه ثبت شده است')
        self.assertEqual(BarberWorkingSchedule.objects.count(), 1)

    def test_editing_into_an_existing_day_has_persian_error(self):
        self.create(days='all')
        sunday = BarberWorkingSchedule.objects.get(day_of_week=7)
        response = self.client.post(reverse('panel:schedule_edit', args=[sunday.pk]), {**self.data, 'day_of_week': 6})
        self.assertContains(response, 'قبلاً برنامه کاری ثبت شده است')
        sunday.refresh_from_db()
        self.assertEqual(sunday.day_of_week, 7)

    def test_invalid_ranges_and_incomplete_breaks_do_not_save(self):
        cases = [
            ({'end_time': '08:00'}, 'ساعت پایان'),
            ({'end_time': '09:00'}, 'ساعت پایان'),
            ({'start_time': '24:00'}, 'ساعت معتبر نیست'),
            ({'end_time': '18:60'}, 'ساعت معتبر نیست'),
            ({'end_time': '6 PM'}, 'ساعت معتبر نیست'),
            ({'break_start_time': '12:00'}, 'شروع و پایان استراحت'),
            ({'break_end_time': '13:00'}, 'شروع و پایان استراحت'),
            ({'break_start_time': '13:00', 'break_end_time': '12:00'}, 'پایان استراحت'),
            ({'break_start_time': '08:00', 'break_end_time': '10:00'}, 'داخل بازه ساعت کاری'),
            ({'slot_duration_minutes': '0'}, '۱'),
        ]
        for changes, message in cases:
            with self.subTest(changes=changes):
                response = self.create(**changes)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['form'].errors)
                if changes != {'slot_duration_minutes': '0'}:
                    self.assertContains(response, message)
                self.assertNotContains(response, 'Constraint')
                self.assertEqual(BarberWorkingSchedule.objects.count(), 0)

    def test_midnight_noon_and_evening_are_unambiguous(self):
        for start, end in [('00:00', '01:00'), ('09:00', '12:00'), ('12:00', '18:00'), ('18:00', '23:59')]:
            with self.subTest(start=start, end=end):
                form = ScheduleCreateForm(data={**self.data, 'start_time': start, 'end_time': end})
                self.assertTrue(form.is_valid(), form.errors)

    def test_invalid_every_day_request_leaves_existing_week_unchanged(self):
        self.create(days='all')
        response = self.create(days='all', end_time='08:00')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(BarberWorkingSchedule.objects.filter(end_time=time(18)).count(), 7)

    def test_every_day_write_failure_rolls_back_all_days(self):
        real_save = BarberWorkingSchedule.save
        calls = []

        def fail_second(schedule, *args, **kwargs):
            calls.append(schedule.day_of_week)
            if len(calls) == 2:
                raise IntegrityError('simulated competing write')
            return real_save(schedule, *args, **kwargs)

        with patch.object(BarberWorkingSchedule, 'save', fail_second):
            response = self.create(days='all')
        self.assertContains(response, 'اطلاعات با رکورد دیگری تداخل دارد')
        self.assertEqual(BarberWorkingSchedule.objects.count(), 0)

    def test_schedule_changes_are_used_by_bot_availability(self):
        self.create(days='all', break_start_time='12:00', break_end_time='13:00')
        date = timezone.localdate() + timedelta(days=1)
        slots = get_available_slots(self.barber, date)
        self.assertIn(time(9), slots)
        self.assertNotIn(time(12), slots)
        self.assertNotIn(time(18), slots)
        schedule = BarberWorkingSchedule.objects.get(day_of_week=date.isoweekday())
        self.client.post(reverse('panel:schedule_edit', args=[schedule.pk]), {
            **self.data, 'day_of_week': date.isoweekday(), 'is_active': '',
        })
        self.assertEqual(get_available_slots(self.barber, date), [])

    def test_list_orders_days_from_saturday_to_friday(self):
        self.create(days='all')
        response = self.client.get(reverse('panel:schedules'))
        self.assertEqual([item.day_of_week for item in response.context['schedules']], [6, 7, 1, 2, 3, 4, 5])

    def test_delete_requires_post(self):
        self.create()
        schedule = BarberWorkingSchedule.objects.get()
        url = reverse('panel:schedule_delete', args=[schedule.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertTrue(BarberWorkingSchedule.objects.filter(pk=schedule.pk).exists())
        self.assertRedirects(self.client.post(url), reverse('panel:schedules'))
        self.assertFalse(BarberWorkingSchedule.objects.exists())

    def test_time_widget_keeps_24_hour_values_on_edit(self):
        self.create(start_time='09:15', end_time='18:45')
        schedule = BarberWorkingSchedule.objects.get()
        form = BarberWorkingSchedulePanelForm(instance=schedule)
        self.assertIn('value="18:45"', str(form['end_time']))
        self.assertIn('dir="ltr"', str(form['end_time']))
        response = self.client.get(reverse('panel:schedule_create'))
        self.assertContains(response, 'هر روز (تمام روزهای هفته)')
        self.assertContains(response, 'panel/time-picker.js')
