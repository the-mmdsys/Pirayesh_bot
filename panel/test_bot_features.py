from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from appointments.models import Barber, BarberPortfolio, BotUser, SalonSettings
from .maintenance import run_job
from .models import BotControl, MaintenanceJob

IMAGE_BYTES = (Path(__file__).resolve().parent / 'static/panel/payizan-logo.png').read_bytes()


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class MediaPanelTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('editor', is_staff=True)
        self.client.force_login(self.staff)
        self.barber = Barber.objects.create(first_name='رضا', last_name='احمدی')
        self.tempdir = TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.media_override = override_settings(MEDIA_ROOT=self.tempdir.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)

    def image(self):
        return SimpleUploadedFile('sample.png', IMAGE_BYTES, content_type='image/png')

    def test_custom_profile_portfolio_edit_hide_reorder_and_delete(self):
        edit = reverse('panel:barber_edit', args=[self.barber.pk])
        self.assertEqual(self.client.post(edit, {
            'first_name': 'رضا', 'last_name': 'احمدی', 'specialty': 'فید و اصلاح', 'experience_years': 8,
            'biography': 'آموزش و سابقه حرفه‌ای', 'description': 'معرفی دلخواه', 'image': self.image(), 'is_active': 'on',
        }).status_code, 302)
        self.barber.refresh_from_db()
        self.assertEqual(self.barber.experience_years, 8)
        gallery = reverse('panel:barber_portfolio', args=[self.barber.pk])
        self.assertRedirects(self.client.post(gallery, {
            'image': self.image(), 'title': 'فید کلاسیک', 'caption': 'نمونه‌کار تازه', 'position': 2, 'is_active': 'on',
        }), gallery)
        work = BarberPortfolio.objects.get()
        self.assertContains(self.client.get(gallery), work.image.url)
        work_edit = reverse('panel:portfolio_edit', args=[self.barber.pk, work.pk])
        self.assertRedirects(self.client.post(work_edit, {'title': 'عنوان تازه', 'caption': 'پنهان', 'position': 5}), gallery)
        work.refresh_from_db()
        self.assertFalse(work.is_active)
        self.assertEqual(work.position, 5)
        work_delete = reverse('panel:portfolio_delete', args=[self.barber.pk, work.pk])
        self.assertEqual(self.client.get(work_delete).status_code, 200)
        self.assertTrue(BarberPortfolio.objects.exists())
        self.assertRedirects(self.client.post(work_delete), gallery)
        self.assertFalse(BarberPortfolio.objects.exists())

    def test_invalid_image_is_rejected_and_work_is_scoped_to_barber(self):
        gallery = reverse('panel:barber_portfolio', args=[self.barber.pk])
        response = self.client.post(gallery, {'image': SimpleUploadedFile('fake.png', b'not-an-image'), 'position': 0})
        self.assertTrue(response.context['form'].errors)
        self.assertFalse(BarberPortfolio.objects.exists())
        other = Barber.objects.create(first_name='علی', last_name='کریمی')
        work = BarberPortfolio.objects.create(barber=other, image=self.image())
        self.assertEqual(self.client.post(reverse('panel:portfolio_delete', args=[self.barber.pk, work.pk])).status_code, 404)
        self.assertTrue(BarberPortfolio.objects.filter(pk=work.pk).exists())

    def test_salon_logo_and_contact_settings_upload(self):
        response = self.client.post(reverse('panel:salon_settings'), {
            'salon_name': 'پیرایش تخصصی پاییزان', 'logo': self.image(), 'contact_intro': 'در کنار شما هستیم',
            'phone': '02112345678', 'reservation_days_ahead': 30, 'social_url': 'https://example.com/salon',
        })
        self.assertRedirects(response, reverse('panel:salon_settings'))
        salon = SalonSettings.objects.get()
        self.assertTrue(salon.logo.storage.exists(salon.logo.name))
        self.assertEqual(salon.contact_intro, 'در کنار شما هستیم')


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class BotControlPanelTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser('owner', 'owner@example.com', 'secret')
        self.staff = User.objects.create_user('staff', is_staff=True)
        self.client.force_login(self.owner)

    def test_switch_is_superuser_only_post_only_and_explicit(self):
        toggle = reverse('panel:bot_toggle')
        self.assertEqual(self.client.get(toggle).status_code, 405)
        self.assertEqual(self.client.post(toggle, {'state': 'invalid'}).status_code, 400)
        self.assertRedirects(self.client.post(toggle, {'state': 'off'}), reverse('panel:bot_control'))
        self.assertFalse(BotControl.current().is_enabled)
        self.client.post(toggle, {'state': 'off'})
        self.assertFalse(BotControl.current().is_enabled)
        self.client.post(toggle, {'state': 'on'})
        self.assertTrue(BotControl.current().is_enabled)
        self.client.force_login(self.staff)
        for name in ['bot_control', 'bot_toggle', 'bot_maintain', 'maintenance_status', 'recovery_email']:
            self.assertEqual(self.client.post(reverse(f'panel:{name}')).status_code, 403)

    def test_sensitive_actions_enforce_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        for name in ['bot_toggle', 'bot_maintain']:
            self.assertEqual(client.post(reverse(f'panel:{name}')).status_code, 403)

    @patch('panel.control_views.launch_job')
    def test_maintenance_starts_once_and_reports_duplicate(self, launch):
        url = reverse('panel:bot_maintain')
        self.client.post(url, {'action': 'optimize'})
        self.client.post(url, {'action': 'optimize'})
        self.assertEqual(MaintenanceJob.objects.count(), 1)
        launch.assert_called_once()
        self.assertTrue(self.client.get(reverse('panel:maintenance_status')).json()['active'])

    @patch('panel.control_views.launch_job', side_effect=OSError('cannot launch'))
    def test_launch_failure_releases_lock(self, launch):
        self.client.post(reverse('panel:bot_maintain'), {'action': 'optimize'})
        job = MaintenanceJob.objects.get()
        self.assertIsNone(job.active)
        self.assertEqual(job.status, MaintenanceJob.Status.FAILED)

    @patch('panel.maintenance.run_command', return_value='')
    def test_optimization_only_removes_expired_sessions_and_keeps_business_data(self, command):
        customer = BotUser.objects.create(bale_user_id=123, full_name='علی احمدی')
        barber = Barber.objects.create(first_name='رضا', last_name='کریمی')
        Session.objects.create(session_key='expired-test', session_data='', expire_date=timezone.now() - timedelta(days=1))
        job = MaintenanceJob.objects.create(requested_by=self.owner)
        run_job(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, MaintenanceJob.Status.SUCCEEDED)
        self.assertFalse(Session.objects.filter(pk='expired-test').exists())
        self.assertTrue(BotUser.objects.filter(pk=customer.pk).exists())
        self.assertTrue(Barber.objects.filter(pk=barber.pk).exists())
        command.assert_called_once_with(['manage.py', 'check'])

    @patch('panel.maintenance.package_updates_available', return_value=True)
    @patch('panel.maintenance.run_command', return_value='Django==5.2.17\n')
    def test_upgrade_records_versions_checks_install_and_requires_restart(self, command, allowed):
        job = MaintenanceJob.objects.create(requested_by=self.owner, upgrade_packages=True)
        with TemporaryDirectory() as root, override_settings(BASE_DIR=Path(root)):
            run_job(job.pk)
            self.assertTrue((Path(root) / '.maintenance' / f'{job.pk}-before.txt').exists())
        job.refresh_from_db()
        self.assertEqual(job.status, MaintenanceJob.Status.SUCCEEDED)
        self.assertTrue(job.restart_required)
        commands = [call.args[0] for call in command.call_args_list]
        self.assertTrue(any('--upgrade' in args and '--no-input' in args for args in commands))
        self.assertIn(['-m', 'pip', 'check'], commands)

    @patch('panel.maintenance.run_command', side_effect=RuntimeError('secret output'))
    def test_worker_failure_is_recorded_without_exposing_subprocess_output(self, command):
        job = MaintenanceJob.objects.create(requested_by=self.owner)
        run_job(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, MaintenanceJob.Status.FAILED)
        self.assertIsNone(job.active)
        self.assertNotIn('secret output', job.summary)
