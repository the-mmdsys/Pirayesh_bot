import re
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import PanelSession, PasswordResetChallenge
from .security import RESET_SESSION_KEY


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PasswordRecoveryTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser('owner', 'owner@example.com', 'previous-password-27')
        self.request_url = reverse('panel:password_reset')
        self.verify_url = reverse('panel:password_reset_verify')
        self.confirm_url = reverse('panel:password_reset_confirm')
        self.password_data = {'new_password1': 'Fresh-salon-secret-843!', 'new_password2': 'Fresh-salon-secret-843!'}

    def issue(self, email='owner@example.com'):
        response = self.client.post(self.request_url, {'email': email})
        self.assertRedirects(response, self.verify_url)
        return re.search(r'\b\d{6}\b', mail.outbox[-1].body).group() if mail.outbox else None

    def test_full_flow_replaces_password_consumes_code_and_invalidates_sessions(self):
        device = Client()
        device.force_login(self.owner)
        device.get(reverse('panel:dashboard'))
        old_key = device.session.session_key
        code = self.issue()
        challenge = PasswordResetChallenge.objects.get()
        self.assertNotEqual(challenge.code_hash, code)
        self.assertRedirects(self.client.post(self.verify_url, {'code': code}), self.confirm_url)
        self.assertRedirects(self.client.post(self.confirm_url, self.password_data), reverse('panel:login'))
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.check_password(self.password_data['new_password1']))
        challenge.refresh_from_db()
        self.assertIsNotNone(challenge.consumed_at)
        self.assertFalse(Session.objects.filter(pk=old_key).exists())
        self.assertRedirects(self.client.post(self.confirm_url, self.password_data), self.request_url)
        self.assertEqual(device.get(reverse('panel:dashboard')).status_code, 302)

    def test_code_required_and_bound_to_requesting_browser(self):
        code = self.issue()
        self.assertRedirects(self.client.post(self.confirm_url, self.password_data), self.request_url)
        stranger = Client()
        self.assertRedirects(stranger.post(self.verify_url, {'code': code}), self.request_url)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.check_password('previous-password-27'))

    def test_expired_code_is_rejected(self):
        code = self.issue()
        PasswordResetChallenge.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        response = self.client.post(self.verify_url, {'code': code})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'منقضی')
        self.assertRedirects(self.client.get(self.confirm_url), self.request_url)

    def test_five_wrong_codes_lock_challenge_even_with_correct_code(self):
        code = self.issue()
        wrong = '111111' if code != '111111' else '222222'
        for _ in range(5):
            self.client.post(self.verify_url, {'code': wrong})
        self.assertEqual(self.client.post(self.verify_url, {'code': code}).status_code, 200)
        self.assertEqual(PasswordResetChallenge.objects.get().attempts, 5)
        self.assertIsNone(PasswordResetChallenge.objects.get().verified_at)

    def test_unknown_staff_inactive_and_shared_email_get_same_response_without_email(self):
        User.objects.create_user('staff', 'staff@example.com', 'secret', is_staff=True)
        User.objects.create_superuser('disabled', 'disabled@example.com', 'secret', is_active=False)
        User.objects.create_superuser('shared1', 'shared@example.com', 'secret')
        User.objects.create_superuser('shared2', 'shared@example.com', 'secret')
        for email in ['missing@example.com', 'staff@example.com', 'disabled@example.com', 'shared@example.com']:
            self.issue(email)
        self.assertEqual(len(mail.outbox), 0)

    def test_email_rate_limit_survives_different_browser_sessions(self):
        for _ in range(3):
            self.client = Client()
            self.issue()
        self.client = Client()
        response = self.client.post(self.request_url, {'email': 'OWNER@EXAMPLE.COM'})
        self.assertContains(response, '۱۵ دقیقه')
        self.assertEqual(len(mail.outbox), 3)

    def test_resend_invalidates_previous_code_and_password_change_invalidates_grant(self):
        self.issue()
        first_id = self.client.session[RESET_SESSION_KEY]
        self.issue()
        self.assertIsNotNone(PasswordResetChallenge.objects.get(pk=first_id).consumed_at)
        code = re.search(r'\b\d{6}\b', mail.outbox[-1].body).group()
        self.client.post(self.verify_url, {'code': code})
        self.owner.set_password('Changed-elsewhere-34')
        self.owner.save()
        self.assertRedirects(self.client.post(self.confirm_url, self.password_data), self.request_url)

    def test_weak_or_mismatched_password_does_not_consume_verified_code(self):
        code = self.issue()
        self.client.post(self.verify_url, {'code': code})
        response = self.client.post(self.confirm_url, {'new_password1': '123', 'new_password2': '123'})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(PasswordResetChallenge.objects.get().consumed_at)

    def test_smtp_failure_keeps_generic_response_and_cannot_reset_password(self):
        with patch('panel.security.send_mail', side_effect=OSError('offline')):
            response = self.client.post(self.request_url, {'email': self.owner.email})
        self.assertRedirects(response, self.verify_url)
        self.assertIsNotNone(PasswordResetChallenge.objects.get().consumed_at)

    def test_recovery_pages_enforce_csrf(self):
        client = Client(enforce_csrf_checks=True)
        for url in [self.request_url, self.verify_url, self.confirm_url]:
            self.assertEqual(client.post(url, self.password_data).status_code, 403)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class SessionManagementTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser('owner', 'owner@example.com', 'secret-owner')
        self.staff = User.objects.create_user('staff', password='secret-staff', is_staff=True)
        self.client.force_login(self.owner)
        self.client.get(reverse('panel:dashboard'), HTTP_USER_AGENT='Test browser', REMOTE_ADDR='127.0.0.2')
        self.owner_session = PanelSession.objects.get(user=self.owner)
        self.other = Client()
        self.other.force_login(self.staff)
        self.other.get(reverse('panel:dashboard'))
        self.staff_session = PanelSession.objects.get(user=self.staff)

    def test_owner_can_view_and_revoke_staff_session_post_only(self):
        response = self.client.get(reverse('panel:sessions'))
        self.assertContains(response, 'Test browser')
        self.assertContains(response, '127.0.0.2')
        self.assertEqual(response.context['sessions'].paginator.count, 2)
        url = reverse('panel:session_revoke', args=[self.staff_session.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertRedirects(self.client.post(url), reverse('panel:sessions'))
        self.assertEqual(self.other.get(reverse('panel:dashboard')).status_code, 302)

    def test_staff_sees_only_their_sessions_and_cannot_revoke_owner(self):
        response = self.other.get(reverse('panel:sessions'))
        self.assertEqual(response.context['sessions'].paginator.count, 1)
        self.assertEqual(self.other.post(reverse('panel:session_revoke', args=[self.owner_session.pk])).status_code, 404)
        self.assertTrue(Session.objects.filter(pk=self.owner_session.session_id).exists())

    def test_current_session_revocation_logs_out(self):
        self.assertRedirects(self.client.post(reverse('panel:session_revoke', args=[self.owner_session.pk])), reverse('panel:login'))
        self.assertEqual(self.client.get(reverse('panel:dashboard')).status_code, 302)

    def test_recovery_email_update_requires_current_password(self):
        url = reverse('panel:recovery_email')
        self.client.post(url, {'email': 'new@example.com', 'current_password': 'wrong'})
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.email, 'owner@example.com')
        self.assertRedirects(self.client.post(url, {'email': 'new@example.com', 'current_password': 'secret-owner'}), url)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.email, 'new@example.com')
