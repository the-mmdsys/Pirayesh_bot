"""Opt-in browser checks; the live server uses Django's isolated test database."""
import os
import re
from pathlib import Path
from unittest import skipUnless
from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core import mail
from django.test import override_settings

from appointments.models import Barber


@skipUnless(os.getenv('PANEL_BROWSER_TESTS') == '1', 'Set PANEL_BROWSER_TESTS=1 to run Playwright checks.')
@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PanelBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        self.media_dir = TemporaryDirectory(prefix='payizan-browser-media-')
        self.addCleanup(self.media_dir.cleanup)
        media_override = override_settings(MEDIA_ROOT=self.media_dir.name)
        media_override.enable()
        self.addCleanup(media_override.disable)
        User.objects.create_user(username='browser_admin', password='browser-test-only', is_staff=True,
                                 is_superuser=self._testMethodName == 'test_password_recovery_gallery_and_bot_controls_in_browser',
                                 email='owner@example.com')
        self.barber = Barber.objects.create(first_name='رضا', last_name='احمدی')
        from playwright.sync_api import sync_playwright
        self.playwright = sync_playwright().start()
        self.addCleanup(self.playwright.stop)
        channel = os.getenv('PANEL_BROWSER_CHANNEL')
        self.browser = self.playwright.chromium.launch(headless=True, **({'channel': channel} if channel else {}))
        self.addCleanup(self.browser.close)
        self.context = self.browser.new_context(viewport={'width': 1366, 'height': 900}, locale='fa-IR')
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.page.set_default_timeout(15000)
        self.js_errors = []
        self.page.on('pageerror', lambda error: self.js_errors.append(str(error)))
        self.artifacts = Path('.artifacts/panel-review')
        self.artifacts.mkdir(parents=True, exist_ok=True)

    def login(self):
        self.page.goto(f'{self.live_server_url}/panel/', wait_until='domcontentloaded')
        self.page.get_by_label('نام کاربری').fill('browser_admin')
        self.page.get_by_label('گذرواژه').fill('browser-test-only')
        self.page.get_by_role('button', name='ورود', exact=True).click()
        self.page.wait_for_url(f'{self.live_server_url}/panel/')

    def open_create(self):
        self.page.goto(f'{self.live_server_url}/panel/schedules/new/', wait_until='domcontentloaded')
        self.page.get_by_label('آرایشگر', exact=True).select_option(str(self.barber.pk))

    def pick(self, label, hour, minute):
        self.page.get_by_role('button', name=f'انتخاب {label}', exact=True).click()
        dialog = self.page.get_by_role('dialog')
        dialog.locator(f'[data-part="hour"] [data-value="{hour}"]').click()
        dialog.locator(f'[data-part="minute"] [data-value="{minute}"]').click()
        dialog.get_by_role('button', name='تأیید ساعت').click()

    def test_desktop_schedule_login_logout_and_error_flow(self):
        self.login()
        self.open_create()
        self.pick('ساعت شروع', 9, 15)
        self.pick('ساعت پایان', 18, 45)
        self.pick('شروع استراحت', 13, 0)
        self.pick('پایان استراحت', 14, 0)
        self.assertEqual(self.page.get_by_label('ساعت پایان', exact=True).input_value(), '18:45')
        self.page.get_by_role('button', name='انتخاب ساعت پایان', exact=True).click()
        self.page.screenshot(path=str(self.artifacts / 'schedule-clock-desktop.png'), full_page=True)
        self.page.keyboard.press('Escape')
        self.page.get_by_role('button', name='ذخیره', exact=True).click()
        self.page.wait_for_url(f'{self.live_server_url}/panel/schedules/')
        self.assertEqual(self.page.locator('tbody tr').count(), 7)
        self.page.screenshot(path=str(self.artifacts / 'schedule-week-desktop.png'), full_page=True)

        sunday = self.page.locator('tbody tr').filter(has_text='یکشنبه')
        sunday.get_by_role('link', name='ویرایش').click()
        self.assertEqual(self.page.get_by_label('ساعت پایان', exact=True).input_value(), '18:45')
        self.page.get_by_label('ساعت شروع', exact=True).fill('۱۰:۰۰')
        self.page.get_by_label('ساعت پایان', exact=True).fill('09:00')
        self.page.get_by_role('button', name='ذخیره', exact=True).click()
        self.page.get_by_text('ساعت پایان باید بعد از ساعت شروع باشد.', exact=False).wait_for()
        self.page.get_by_label('ساعت پایان', exact=True).fill('۱۸:۴۵')
        self.page.get_by_role('button', name='ذخیره', exact=True).click()
        self.page.wait_for_url(f'{self.live_server_url}/panel/schedules/')
        self.assertIn('10:00', self.page.locator('tbody tr').filter(has_text='یکشنبه').inner_text())
        self.assertIn('09:15', self.page.locator('tbody tr').filter(has_text='شنبه').first.inner_text())
        self.assertEqual(self.page.locator('a[href^="/admin/"]').count(), 0)
        self.assertEqual(self.page.request.get(f'{self.live_server_url}/admin/').status, 404)
        self.page.get_by_role('button', name='خروج', exact=True).click()
        self.page.wait_for_url(f'{self.live_server_url}/panel/login/')
        self.assertEqual(self.js_errors, [])

    def test_mobile_picker_keyboard_cancel_and_clear(self):
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.login()
        self.open_create()
        self.page.get_by_role('button', name='انتخاب ساعت شروع', exact=True).click()
        dialog = self.page.get_by_role('dialog')
        self.page.keyboard.press('ArrowDown')
        self.page.keyboard.press('Tab')
        self.page.keyboard.press('ArrowDown')
        dialog.get_by_role('button', name='تأیید ساعت').click()
        self.assertEqual(self.page.get_by_label('ساعت شروع', exact=True).input_value(), '10:01')
        self.pick('ساعت پایان', 20, 7)
        self.page.get_by_role('button', name='انتخاب ساعت پایان', exact=True).click()
        dialog.locator('[data-part="hour"] [data-value="22"]').click()
        self.page.screenshot(path=str(self.artifacts / 'schedule-clock-mobile.png'), full_page=True)
        bounds = dialog.bounding_box()
        self.assertGreaterEqual(bounds['x'], 0)
        self.assertLessEqual(bounds['x'] + bounds['width'], 390)
        dialog.get_by_role('button', name='انصراف', exact=True).click()
        self.assertEqual(self.page.get_by_label('ساعت پایان', exact=True).input_value(), '20:07')
        self.pick('شروع استراحت', 13, 0)
        self.page.get_by_role('button', name='انتخاب شروع استراحت', exact=True).click()
        dialog.get_by_role('button', name='پاک کردن ساعت').click()
        self.assertEqual(self.page.get_by_label('شروع استراحت', exact=True).input_value(), '')
        self.assertEqual(self.js_errors, [])

    def test_full_day_block_disables_time_picker(self):
        self.login()
        self.page.goto(f'{self.live_server_url}/panel/blocked-times/new/', wait_until='domcontentloaded')
        self.page.get_by_label('کل روز بسته است؟', exact=True).check()
        self.assertTrue(self.page.get_by_label('ساعت شروع', exact=True).is_disabled())
        self.assertTrue(self.page.get_by_role('button', name='انتخاب ساعت پایان', exact=True).is_disabled())
        self.page.get_by_label('کل روز بسته است؟', exact=True).uncheck()
        self.assertTrue(self.page.get_by_label('ساعت شروع', exact=True).is_enabled())
        self.pick('ساعت شروع', 12, 30)
        self.assertEqual(self.page.get_by_label('ساعت شروع', exact=True).input_value(), '12:30')
        self.assertEqual(self.js_errors, [])

    def test_password_recovery_gallery_and_bot_controls_in_browser(self):
        # Assets and flows must work with all external requests blocked.
        self.page.route(re.compile(r'^https://'), lambda route: route.abort())
        self.page.goto(f'{self.live_server_url}/panel/login/')
        self.page.screenshot(path=str(self.artifacts / 'payizan-login-desktop.png'), full_page=True)
        self.page.get_by_role('link', name='رمز عبور را فراموش کرده‌اید؟').click()
        self.page.get_by_label('ایمیل حساب مدیر اصلی').fill('owner@example.com')
        self.page.get_by_role('button', name='ارسال کد تأیید').click()
        self.page.wait_for_url('**/password-reset/code/')
        code = re.search(r'\b\d{6}\b', mail.outbox[-1].body).group()
        self.page.get_by_label('کد تأیید شش‌رقمی').fill(code)
        self.page.get_by_role('button', name='تأیید و ادامه').click()
        self.page.wait_for_url('**/password-reset/new/')
        self.page.locator('[name="new_password1"]').fill('Fresh-salon-safe-9482!')
        self.page.locator('[name="new_password2"]').fill('Fresh-salon-safe-9482!')
        self.page.get_by_role('button', name='ذخیره رمز جدید').click()
        self.page.wait_for_url('**/panel/login/')
        self.page.get_by_label('نام کاربری').fill('browser_admin')
        self.page.get_by_label('گذرواژه', exact=True).fill('Fresh-salon-safe-9482!')
        self.page.get_by_role('button', name='ورود', exact=True).click()
        self.page.wait_for_url(f'{self.live_server_url}/panel/')
        self.page.screenshot(path=str(self.artifacts / 'payizan-dashboard-desktop.png'), full_page=True)
        self.page.goto(f'{self.live_server_url}/panel/barbers/{self.barber.pk}/portfolio/')
        self.page.locator('input[type=file]').set_input_files('panel/static/panel/payizan-logo.png')
        self.page.get_by_label('عنوان نمونه‌کار').fill('نمونه‌کار تست مرورگر')
        self.page.get_by_role('button', name='آپلود و ذخیره نمونه‌کار').click()
        self.page.get_by_role('heading', name='نمونه‌کار تست مرورگر').wait_for()
        self.assertEqual(self.page.locator('article.portfolio-card').count(), 1)
        self.page.screenshot(path=str(self.artifacts / 'payizan-portfolio-desktop.png'), full_page=True)
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.page.goto(f'{self.live_server_url}/panel/bot/')
        self.page.get_by_role('button', name='خاموش کردن موقت', exact=True).click()
        self.page.get_by_role('button', name='روشن کردن ربات', exact=True).wait_for()
        self.page.get_by_role('button', name='روشن کردن ربات', exact=True).click()
        self.page.get_by_role('button', name='خاموش کردن موقت', exact=True).wait_for()
        self.page.screenshot(path=str(self.artifacts / 'payizan-controls-mobile.png'), full_page=True)
        self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth > innerWidth'))
        self.page.goto(f'{self.live_server_url}/panel/sessions/')
        self.page.get_by_role('button', name='خروج از همین دستگاه').wait_for()
        self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth > innerWidth'))
        self.page.screenshot(path=str(self.artifacts / 'payizan-sessions-mobile.png'), full_page=True)
        self.assertEqual(self.js_errors, [])
