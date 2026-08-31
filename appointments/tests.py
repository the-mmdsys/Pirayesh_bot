from datetime import date, time, timedelta

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.test import RequestFactory
from django.test import TestCase
from django.utils import timezone

from appointments.admin import AppointmentAdmin, AppointmentDateFilter
from appointments.models import Appointment, Barber, BarberWorkingSchedule, BlockedTime, BotUser
from appointments.forms import AppointmentAdminForm, BlockedTimeAdminForm
from appointments.services.availability import (
    get_available_dates,
    get_available_slots,
    is_slot_available,
)
from appointments.utils.date_utils import gregorian_to_jalali, jalali_to_gregorian


def next_weekday(weekday):
    current_date = timezone.localdate()
    days_until_weekday = (weekday - current_date.isoweekday()) % 7
    if days_until_weekday == 0:
        days_until_weekday = 7
    return current_date + timedelta(days=days_until_weekday)


class AvailabilityServiceTests(TestCase):
    def setUp(self):
        self.barber = Barber.objects.create(first_name='Ali', last_name='Ahmadi')
        self.user = BotUser.objects.create(bale_user_id=1001, first_name='Reza')
        self.target_date = next_weekday(BarberWorkingSchedule.Weekday.MONDAY)
        BarberWorkingSchedule.objects.create(
            barber=self.barber,
            day_of_week=BarberWorkingSchedule.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(12, 0),
            slot_duration_minutes=30,
            break_start_time=time(10, 0),
            break_end_time=time(10, 30),
        )

    def test_get_available_slots_uses_schedule_and_break_time(self):
        slots = get_available_slots(self.barber, self.target_date)

        self.assertEqual(slots, [time(9, 0), time(9, 30), time(10, 30), time(11, 0), time(11, 30)])

    def test_get_available_slots_excludes_booked_appointments(self):
        Appointment.objects.create(
            user=self.user,
            barber=self.barber,
            date=self.target_date,
            start_time=time(9, 30),
            status=Appointment.Status.BOOKED,
        )

        slots = get_available_slots(self.barber, self.target_date)

        self.assertNotIn(time(9, 30), slots)
        self.assertIn(time(9, 0), slots)

    def test_get_available_slots_excludes_blocked_times(self):
        BlockedTime.objects.create(
            barber=self.barber,
            date=self.target_date,
            start_time=time(11, 0),
            end_time=time(12, 0),
        )

        slots = get_available_slots(self.barber, self.target_date)

        self.assertNotIn(time(11, 0), slots)
        self.assertNotIn(time(11, 30), slots)

    def test_get_available_slots_returns_empty_for_full_day_block(self):
        BlockedTime.objects.create(
            barber=self.barber,
            date=self.target_date,
            is_full_day=True,
        )

        self.assertEqual(get_available_slots(self.barber, self.target_date), [])

    def test_get_available_dates_returns_dates_that_have_slots(self):
        available_dates = get_available_dates(
            self.barber,
            start_date=self.target_date,
            days_ahead=1,
        )

        self.assertEqual(available_dates, [self.target_date])

    def test_inactive_barber_has_no_available_slots(self):
        self.barber.is_active = False
        self.barber.save()

        self.assertFalse(is_slot_available(self.barber, self.target_date, time(9, 0)))

    def test_past_dates_are_not_available(self):
        past_date = timezone.localdate() - timedelta(days=1)

        self.assertEqual(get_available_slots(self.barber, past_date), [])


class JalaliDateUtilsTests(TestCase):
    def test_gregorian_to_jalali(self):
        self.assertEqual(gregorian_to_jalali(date(2026, 8, 30)), '1405/06/08')

    def test_valid_jalali_to_gregorian(self):
        self.assertEqual(jalali_to_gregorian('1405/06/08'), date(2026, 8, 30))

    def test_invalid_jalali_date_is_rejected(self):
        invalid_values = ['1405/15/50', 'abc', '1405/6']

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    jalali_to_gregorian(value)


class AppointmentValidationTests(TestCase):
    def setUp(self):
        self.barber = Barber.objects.create(first_name='Ali', last_name='Ahmadi')
        self.user = BotUser.objects.create(bale_user_id=2001, first_name='Reza')

    def test_creating_appointment_for_yesterday_is_rejected(self):
        appointment = Appointment(
            user=self.user,
            barber=self.barber,
            date=timezone.localdate() - timedelta(days=1),
            start_time=time(12, 0),
        )

        with self.assertRaises(ValidationError):
            appointment.full_clean()

    def test_creating_appointment_for_past_time_today_is_rejected(self):
        appointment = Appointment(
            user=self.user,
            barber=self.barber,
            date=timezone.localdate(),
            start_time=time(0, 0),
        )

        with self.assertRaises(ValidationError):
            appointment.full_clean()

    def test_creating_appointment_for_future_time_is_allowed(self):
        appointment = Appointment(
            user=self.user,
            barber=self.barber,
            date=timezone.localdate() + timedelta(days=1),
            start_time=time(12, 0),
        )

        appointment.full_clean()

    def test_existing_historical_appointment_status_can_be_edited(self):
        old_appointment = Appointment(
            user=self.user,
            barber=self.barber,
            date=timezone.localdate() - timedelta(days=5),
            start_time=time(12, 0),
            status=Appointment.Status.BOOKED,
        )
        Appointment.objects.bulk_create([old_appointment])

        appointment = Appointment.objects.get(user=self.user, barber=self.barber)
        appointment.status = Appointment.Status.COMPLETED
        appointment.save()

        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.COMPLETED)


class AdminJalaliDateFormTests(TestCase):
    def setUp(self):
        self.barber = Barber.objects.create(first_name='Ali', last_name='Ahmadi')
        self.user = BotUser.objects.create(bale_user_id=3001, first_name='Reza')
        self.future_date = timezone.localdate() + timedelta(days=1)

    def test_appointment_admin_form_saves_gregorian_date_from_jalali_input(self):
        form = AppointmentAdminForm(
            data={
                'user': self.user.id,
                'barber': self.barber.id,
                'date': gregorian_to_jalali(self.future_date),
                'start_time': '12:00',
                'end_time': '',
                'status': Appointment.Status.BOOKED,
                'cancelled_at': '',
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        appointment = form.save()
        self.assertEqual(appointment.date, self.future_date)

    def test_blocked_time_admin_form_saves_gregorian_date_from_jalali_input(self):
        form = BlockedTimeAdminForm(
            data={
                'barber': self.barber.id,
                'date': gregorian_to_jalali(self.future_date),
                'is_full_day': 'on',
                'start_time': '',
                'end_time': '',
                'reason': '',
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        blocked_time = form.save()
        self.assertEqual(blocked_time.date, self.future_date)


class AppointmentAdminTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.model_admin = AppointmentAdmin(Appointment, admin.site)
        self.barber = Barber.objects.create(first_name='Ali', last_name='Ahmadi')
        self.user = BotUser.objects.create(
            bale_user_id=4001,
            first_name='Reza',
            last_name='Karimi',
            phone='09125550000',
        )
        self.today_appointment = Appointment(
            user=self.user,
            barber=self.barber,
            date=timezone.localdate(),
            start_time=time(23, 59),
            status=Appointment.Status.BOOKED,
        )
        self.future_appointment = Appointment.objects.create(
            user=self.user,
            barber=self.barber,
            date=timezone.localdate() + timedelta(days=1),
            start_time=time(12, 0),
            status=Appointment.Status.BOOKED,
        )
        Appointment.objects.bulk_create([self.today_appointment])
        self.today_appointment = Appointment.objects.get(date=timezone.localdate())

    def test_today_filter_returns_only_today_appointments(self):
        request = self.factory.get('/admin/appointments/appointment/', {'appointment_date': 'today'})
        date_filter = AppointmentDateFilter(
            request,
            {'appointment_date': ['today']},
            Appointment,
            self.model_admin,
        )

        queryset = date_filter.queryset(request, Appointment.objects.all())

        self.assertIn(self.today_appointment, queryset)
        self.assertNotIn(self.future_appointment, queryset)

    def test_admin_search_finds_appointment_by_customer_phone(self):
        request = self.factory.get('/admin/appointments/appointment/')

        queryset, may_have_duplicates = self.model_admin.get_search_results(
            request,
            Appointment.objects.all(),
            '09125550000',
        )

        self.assertIn(self.future_appointment, queryset)
        self.assertFalse(may_have_duplicates)

    def test_admin_jalali_date_column_uses_jalali_format(self):
        self.assertEqual(
            self.model_admin.jalali_date(self.future_appointment),
            gregorian_to_jalali(self.future_appointment.date),
        )

    def test_admin_actions_update_appointment_status(self):
        request = self.factory.post('/admin/appointments/appointment/')

        self.model_admin.mark_completed(request, Appointment.objects.filter(id=self.future_appointment.id))
        self.future_appointment.refresh_from_db()
        self.assertEqual(self.future_appointment.status, Appointment.Status.COMPLETED)

        self.model_admin.mark_no_show(request, Appointment.objects.filter(id=self.future_appointment.id))
        self.future_appointment.refresh_from_db()
        self.assertEqual(self.future_appointment.status, Appointment.Status.NO_SHOW)

        self.model_admin.mark_cancelled_by_admin(request, Appointment.objects.filter(id=self.future_appointment.id))
        self.future_appointment.refresh_from_db()
        self.assertEqual(self.future_appointment.status, Appointment.Status.CANCELLED_BY_ADMIN)
        self.assertIsNotNone(self.future_appointment.cancelled_at)
