from datetime import time, timedelta
from tempfile import TemporaryDirectory
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment, Barber, BarberWorkingSchedule, BlockedTime, BotUser, SalonSettings
from appointments.services.availability import get_available_slots
from appointments.utils.date_utils import gregorian_to_jalali


class PanelAuthenticationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(username='staff', password='test-panel-password', is_staff=True)
        cls.regular = User.objects.create_user(username='regular', password='test-panel-password')
        cls.inactive = User.objects.create_user(username='inactive', password='test-panel-password', is_staff=True, is_active=False)
        cls.superuser = User.objects.create_superuser(username='owner', password='test-panel-password')

    def test_login_page_is_persian_and_has_no_admin_links(self):
        response = self.client.get(reverse('panel:login'))
        self.assertContains(response, 'ورود به پنل آرایشگاه')
        self.assertNotContains(response, '/admin/')

    def test_staff_login_returns_to_requested_panel_page(self):
        response = self.client.post(reverse('panel:login'), {
            'username': 'staff', 'password': 'test-panel-password', 'next': '/panel/schedules/',
        })
        self.assertRedirects(response, '/panel/schedules/')

    def test_login_refuses_redirect_outside_panel(self):
        for target in ('/admin/', 'https://example.com/', '//example.com/', '/panel/login/', '/panel/logout/'):
            with self.subTest(target=target):
                response = self.client.post(reverse('panel:login'), {
                    'username': 'staff', 'password': 'test-panel-password', 'next': target,
                })
                self.assertRedirects(response, reverse('panel:dashboard'))
                self.client.logout()

    def test_invalid_regular_and_inactive_logins_have_persian_errors(self):
        for username, password in [('staff', 'wrong'), ('regular', 'test-panel-password'), ('inactive', 'test-panel-password')]:
            with self.subTest(username=username):
                response = self.client.post(reverse('panel:login'), {'username': username, 'password': password})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['form'].errors)
                self.assertNotIn('_auth_user_id', self.client.session)
                self.assertNotContains(response, 'Please')

    def test_authenticated_staff_login_page_redirects_without_loop(self):
        self.client.force_login(self.staff)
        self.assertRedirects(self.client.get(reverse('panel:login')), reverse('panel:dashboard'))

    def test_logout_requires_post_and_clears_the_session(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('panel:logout')).status_code, 405)
        self.assertIn('_auth_user_id', self.client.session)
        self.assertRedirects(self.client.post(reverse('panel:logout')), reverse('panel:login'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_csrf_is_required_for_login_and_logout(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse('panel:login'), {'username': 'staff', 'password': 'test-panel-password'}).status_code, 403)
        client.force_login(self.staff)
        self.assertEqual(client.post(reverse('panel:logout')).status_code, 403)
        client.get(reverse('panel:dashboard'))
        self.assertEqual(client.post(reverse('panel:logout'), {'csrfmiddlewaretoken': client.cookies['csrftoken'].value}).status_code, 302)

    def test_django_admin_is_unavailable_even_to_a_superuser(self):
        for user in (None, self.staff, self.superuser):
            self.client.logout()
            if user:
                self.client.force_login(user)
            for path in ('/admin/', '/admin/login/', '/admin/auth/user/', '/admin/appointments/appointment/'):
                with self.subTest(user=user, path=path):
                    self.assertEqual(self.client.get(path).status_code, 404)

    def test_all_panel_routes_require_staff_access_for_get_and_post(self):
        names = [
            'dashboard', 'today_appointments', 'appointments', 'appointment_create',
            'barbers', 'barber_create', 'schedules', 'schedule_create',
            'blocked_times', 'blocked_time_create', 'users', 'salon_settings',
        ]
        detail_names = ['appointment_edit', 'appointment_cancel', 'barber_edit', 'barber_toggle',
                        'schedule_edit', 'schedule_delete', 'blocked_time_edit', 'blocked_time_delete']
        urls = [reverse(f'panel:{name}') for name in names]
        urls += [reverse(f'panel:{name}', args=[999]) for name in detail_names]
        for user in (None, self.regular):
            self.client.logout()
            if user:
                self.client.force_login(user)
            for url in urls:
                for method in ('get', 'post'):
                    with self.subTest(user=user, url=url, method=method):
                        response = getattr(self.client, method)(url)
                        self.assertEqual(response.status_code, 302)
                        self.assertTrue(response['Location'].startswith('/panel/login/'))


class PanelOperationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(username='operations', is_staff=True)
        cls.barber = Barber.objects.create(first_name='رضا', last_name='کریمی')
        cls.user = BotUser.objects.create(bale_user_id=98765, first_name='علی', last_name='رضایی', phone='09123456789')

    def setUp(self):
        self.client.force_login(self.staff)
        self.date = timezone.localdate() + timedelta(days=1)
        self.appointment_data = {
            'user': self.user.pk, 'barber': self.barber.pk, 'date': gregorian_to_jalali(self.date),
            'start_time': '10:00', 'end_time': '11:00', 'status': Appointment.Status.BOOKED,
        }

    def create_appointment(self, **kwargs):
        response = self.client.post(reverse('panel:appointment_create'), {**self.appointment_data, **kwargs})
        self.assertRedirects(response, reverse('panel:appointments'))
        return Appointment.objects.latest('pk')

    def test_manual_appointment_edit_and_cancel(self):
        appointment = self.create_appointment()
        edit = reverse('panel:appointment_edit', args=[appointment.pk])
        self.assertEqual(self.client.get(edit).status_code, 200)
        response = self.client.post(edit, {**self.appointment_data, 'end_time': '11:30'})
        self.assertRedirects(response, reverse('panel:appointments'))
        appointment.refresh_from_db()
        self.assertEqual(appointment.end_time, time(11, 30))
        cancel = reverse('panel:appointment_cancel', args=[appointment.pk])
        self.assertEqual(self.client.get(cancel).status_code, 200)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.BOOKED)
        self.assertRedirects(self.client.post(cancel), reverse('panel:appointments'))
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.CANCELLED_BY_ADMIN)
        self.assertIsNotNone(appointment.cancelled_at)

    def test_cancel_does_not_change_completed_appointment(self):
        appointment = self.create_appointment(status=Appointment.Status.COMPLETED)
        self.client.post(reverse('panel:appointment_cancel', args=[appointment.pk]))
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.COMPLETED)

    def test_rebooking_clears_cancellation_timestamp(self):
        appointment = self.create_appointment(status=Appointment.Status.CANCELLED_BY_ADMIN)
        self.client.post(reverse('panel:appointment_edit', args=[appointment.pk]), self.appointment_data)
        appointment.refresh_from_db()
        self.assertIsNone(appointment.cancelled_at)

    def test_invalid_appointment_end_and_past_dates_have_persian_errors(self):
        for change, text in [
            ({'end_time': '09:00'}, 'ساعت پایان نوبت'),
            ({'end_time': '10:00'}, 'ساعت پایان نوبت'),
            ({'date': '1405/13/01'}, 'تاریخ شمسی معتبر نیست'),
            ({'date': gregorian_to_jalali(timezone.localdate() - timedelta(days=1))}, 'تاریخ گذشته'),
        ]:
            with self.subTest(change=change):
                response = self.client.post(reverse('panel:appointment_create'), {**self.appointment_data, **change})
                self.assertContains(response, text)
        self.assertEqual(Appointment.objects.count(), 0)

    def test_manual_overlapping_appointments_are_rejected(self):
        self.create_appointment()
        response = self.client.post(reverse('panel:appointment_create'), {**self.appointment_data, 'start_time': '10:30', 'end_time': '11:30'})
        self.assertContains(response, 'تداخل دارد')
        self.assertEqual(Appointment.objects.count(), 1)

    def test_appointments_filters_and_malformed_filter_values(self):
        appointment = self.create_appointment()
        response = self.client.get(reverse('panel:appointments'), {'barber': self.barber.pk, 'status': 'booked', 'q': 'رضایی'})
        self.assertEqual(list(response.context['appointments']), [appointment])
        for invalid in ('abc', '²', '9' * 30, '-1'):
            with self.subTest(invalid=invalid):
                response = self.client.get(reverse('panel:appointments'), {'barber': invalid})
                self.assertContains(response, 'آرایشگر انتخاب‌شده معتبر نیست')

    def test_dashboard_does_not_count_cancelled_appointments_as_upcoming(self):
        self.create_appointment(status=Appointment.Status.CANCELLED_BY_ADMIN)
        booked = self.create_appointment(start_time='12:00', end_time='12:30')
        response = self.client.get(reverse('panel:dashboard'))
        self.assertEqual(response.context['stats'][1]['value'], 1)
        self.assertEqual(list(response.context['upcoming_appointments']), [booked])
        self.assertNotContains(response, '/admin/')

    def test_today_page_excludes_future_appointments(self):
        self.create_appointment()
        response = self.client.get(reverse('panel:today_appointments'))
        self.assertEqual(list(response.context['appointments']), [])

    def test_barber_create_edit_search_and_toggle(self):
        response = self.client.post(reverse('panel:barber_create'), {'first_name': 'حسن', 'last_name': 'محمدی', 'description': 'اصلاح مو', 'is_active': 'on'})
        self.assertRedirects(response, reverse('panel:barbers'))
        barber = Barber.objects.get(first_name='حسن')
        edit = reverse('panel:barber_edit', args=[barber.pk])
        self.assertEqual(self.client.get(edit).status_code, 200)
        self.assertRedirects(self.client.post(edit, {'first_name': 'حسین', 'last_name': 'محمدی', 'is_active': 'on'}), reverse('panel:barbers'))
        response = self.client.get(reverse('panel:barbers'), {'q': 'حسین'})
        self.assertContains(response, 'حسین')
        self.assertNotContains(response, 'رضا کریمی')
        toggle = reverse('panel:barber_toggle', args=[barber.pk])
        self.client.get(toggle)
        barber.refresh_from_db()
        self.assertTrue(barber.is_active)
        self.client.post(toggle)
        barber.refresh_from_db()
        self.assertFalse(barber.is_active)

    def test_barber_image_upload_is_saved_and_rendered(self):
        with TemporaryDirectory(prefix='panel-upload-test-') as media_dir, override_settings(MEDIA_ROOT=media_dir):
            upload = SimpleUploadedFile('photo.png', Path('panel/static/panel/payizan-logo.png').read_bytes(), content_type='image/png')
            response = self.client.post(reverse('panel:barber_edit', args=[self.barber.pk]), {
                'first_name': self.barber.first_name, 'last_name': self.barber.last_name, 'is_active': 'on', 'image': upload,
            })
            self.assertRedirects(response, reverse('panel:barbers'))
            self.barber.refresh_from_db()
            self.assertTrue(self.barber.image.storage.exists(self.barber.image.name))
            self.assertContains(self.client.get(reverse('panel:barbers')), self.barber.image.url)

    def test_empty_barber_form_has_persian_errors(self):
        response = self.client.post(reverse('panel:barber_create'), {})
        self.assertTrue(response.context['form'].errors)
        self.assertNotContains(response, 'This field')

    def test_blocked_time_create_edit_and_delete(self):
        data = {'barber': self.barber.pk, 'date': gregorian_to_jalali(self.date), 'start_time': '12:00', 'end_time': '13:00', 'reason': 'استراحت'}
        response = self.client.post(reverse('panel:blocked_time_create'), data)
        self.assertRedirects(response, reverse('panel:blocked_times'))
        block = BlockedTime.objects.get()
        self.assertEqual(block.date, self.date)
        edit = reverse('panel:blocked_time_edit', args=[block.pk])
        self.assertEqual(self.client.get(edit).status_code, 200)
        self.assertRedirects(self.client.post(edit, {**data, 'end_time': '14:00'}), reverse('panel:blocked_times'))
        block.refresh_from_db()
        self.assertEqual(block.end_time, time(14))
        delete = reverse('panel:blocked_time_delete', args=[block.pk])
        self.assertEqual(self.client.get(delete).status_code, 200)
        self.assertTrue(BlockedTime.objects.exists())
        self.assertRedirects(self.client.post(delete), reverse('panel:blocked_times'))
        self.assertFalse(BlockedTime.objects.exists())

    def test_full_day_block_ignores_stale_times_and_closes_salon_for_bot(self):
        BarberWorkingSchedule.objects.create(barber=self.barber, day_of_week=self.date.isoweekday(), start_time=time(9), end_time=time(18))
        response = self.client.post(reverse('panel:blocked_time_create'), {
            'barber': '', 'date': gregorian_to_jalali(self.date), 'is_full_day': 'on', 'start_time': 'invalid', 'end_time': '08:00',
        })
        self.assertRedirects(response, reverse('panel:blocked_times'))
        block = BlockedTime.objects.get()
        self.assertIsNone(block.start_time)
        self.assertIsNone(block.end_time)
        self.assertEqual(get_available_slots(self.barber, self.date), [])

    def test_partial_block_requires_valid_start_and_end(self):
        for changes in ({}, {'start_time': '12:00'}, {'start_time': '12:00', 'end_time': '11:00'}):
            with self.subTest(changes=changes):
                response = self.client.post(reverse('panel:blocked_time_create'), {'date': gregorian_to_jalali(self.date), **changes})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['form'].errors)
                self.assertNotContains(response, 'End time')
                self.assertNotContains(response, 'Constraint')
        self.assertFalse(BlockedTime.objects.exists())

    def test_users_search_by_name_phone_id_and_non_decimal_numbers(self):
        for query in ('علی', 'رضایی', '0912', '98765'):
            with self.subTest(query=query):
                response = self.client.get(reverse('panel:users'), {'q': query})
                self.assertContains(response, self.user.phone)
        for query in ('²', '9' * 30):
            self.assertEqual(self.client.get(reverse('panel:users'), {'q': query}).status_code, 200)

    def test_settings_update_existing_row_and_reject_invalid_values(self):
        settings = SalonSettings.objects.create(salon_name='قدیمی')
        data = {'salon_name': 'جدید', 'phone': '', 'address': '', 'working_hours_text': '', 'location_url': '', 'reservation_days_ahead': '14'}
        self.assertRedirects(self.client.post(reverse('panel:salon_settings'), data), reverse('panel:salon_settings'))
        settings.refresh_from_db()
        self.assertEqual(settings.salon_name, 'جدید')
        self.assertEqual(SalonSettings.objects.count(), 1)
        for change in ({'reservation_days_ahead': '0'}, {'location_url': 'not a url'}):
            response = self.client.post(reverse('panel:salon_settings'), {**data, **change})
            self.assertTrue(response.context['form'].errors)
            self.assertNotContains(response, 'Enter a valid')

    def test_missing_objects_return_404(self):
        for name in ('appointment_edit', 'appointment_cancel', 'barber_edit', 'barber_toggle', 'schedule_edit', 'schedule_delete', 'blocked_time_edit', 'blocked_time_delete'):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(f'panel:{name}', args=[9999])).status_code, 404)

    def test_form_back_link_stays_inside_panel(self):
        response = self.client.get(reverse('panel:barber_create'), HTTP_REFERER='https://example.com/')
        self.assertNotContains(response, 'https://example.com/')
        self.assertContains(response, 'href="/panel/barbers/"')
