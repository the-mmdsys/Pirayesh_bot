import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment, Barber, BotUser, SalonSettings
from appointments.utils.date_utils import gregorian_to_jalali


class PanelAccessTests(TestCase):
    def test_anonymous_user_is_redirected_to_admin_login(self):
        response = self.client.get(reverse('panel:dashboard'))

        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])

    def test_non_staff_user_is_redirected_to_admin_login(self):
        user = User.objects.create_user(username='normal', password='pass12345')
        self.client.force_login(user)

        response = self.client.get(reverse('panel:dashboard'))

        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])

    def test_staff_user_can_see_dashboard(self):
        user = User.objects.create_user(username='staff', password='pass12345', is_staff=True)
        self.client.force_login(user)

        response = self.client.get(reverse('panel:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'داشبورد')

    def test_staff_user_can_open_main_panel_pages(self):
        user = User.objects.create_user(username='staff', password='pass12345', is_staff=True)
        self.client.force_login(user)
        page_names = [
            'panel:dashboard',
            'panel:today_appointments',
            'panel:appointments',
            'panel:barbers',
            'panel:schedules',
            'panel:blocked_times',
            'panel:users',
            'panel:salon_settings',
        ]

        for page_name in page_names:
            with self.subTest(page_name=page_name):
                response = self.client.get(reverse(page_name))
                self.assertEqual(response.status_code, 200)


class PanelAppointmentTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='staff', password='pass12345', is_staff=True)
        self.client.force_login(self.staff)
        self.bot_user = BotUser.objects.create(
            bale_user_id=123456,
            first_name='علی',
            last_name='رضایی',
            phone='09120000000',
        )
        self.barber = Barber.objects.create(first_name='رضا', last_name='احمدی', is_active=True)

    def test_appointments_list_can_search_by_customer_phone(self):
        appointment_date = timezone.localdate() + datetime.timedelta(days=1)
        Appointment.objects.create(
            user=self.bot_user,
            barber=self.barber,
            date=appointment_date,
            start_time=datetime.time(10, 0),
            status=Appointment.Status.BOOKED,
        )

        response = self.client.get(reverse('panel:appointments'), {'q': '0912'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '09120000000')
        self.assertContains(response, gregorian_to_jalali(appointment_date))

    def test_manual_appointment_form_accepts_jalali_date_and_saves_gregorian_date(self):
        appointment_date = timezone.localdate() + datetime.timedelta(days=2)

        response = self.client.post(
            reverse('panel:appointment_create'),
            {
                'user': self.bot_user.pk,
                'barber': self.barber.pk,
                'date': gregorian_to_jalali(appointment_date),
                'start_time': '11:00',
                'end_time': '11:30',
                'status': Appointment.Status.BOOKED,
            },
        )

        self.assertRedirects(response, reverse('panel:appointments'))
        appointment = Appointment.objects.get()
        self.assertEqual(appointment.date, appointment_date)
        self.assertEqual(appointment.start_time, datetime.time(11, 0))


class PanelSettingsTests(TestCase):
    def setUp(self):
        staff = User.objects.create_user(username='staff', password='pass12345', is_staff=True)
        self.client.force_login(staff)

    def test_salon_settings_page_can_create_settings(self):
        response = self.client.post(
            reverse('panel:salon_settings'),
            {
                'salon_name': 'آرایشگاه تست',
                'phone': '02100000000',
                'address': 'تهران',
                'working_hours_text': 'شنبه تا پنجشنبه ۱۰ تا ۲۰',
                'location_url': '',
                'reservation_days_ahead': 30,
            },
        )

        self.assertRedirects(response, reverse('panel:salon_settings'))
        self.assertEqual(SalonSettings.objects.get().salon_name, 'آرایشگاه تست')
