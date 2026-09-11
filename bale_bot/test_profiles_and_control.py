import json
from datetime import time, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from appointments.models import Barber, BarberPortfolio, BarberWorkingSchedule, BotConversationState, BotUser
from bale_bot.client import BaleAPIError, BaleBotClient
from bale_bot.handlers import handle_callback_query, handle_message, handle_update
from bale_bot.media import send_image_card
from bale_bot.menu import MAIN_MENU_CONTACT, MAIN_MENU_PROFILE, MAIN_MENU_RESERVE
from bale_bot.reservation_flow import RESERVATION_CONFIRM_TEXT, format_barber_label
from bale_bot.test_handlers import FakeClient, make_callback, make_message
from bale_bot.tests import FakeSession
from appointments.utils.date_utils import gregorian_to_jalali
from panel.models import BotControl


class ProfileAndControlTests(TestCase):
    def setUp(self):
        self.bot = FakeClient()
        self.barber = Barber.objects.create(first_name='رضا', last_name='احمدی', specialty='فید', experience_years=9, biography='سوابق حرفه‌ای')
        cache.clear()
        self.tempdir = TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.media_override = override_settings(MEDIA_ROOT=self.tempdir.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)

    def image(self):
        return SimpleUploadedFile('sample.png', Path('panel/static/panel/payizan-logo.png').read_bytes(), content_type='image/png')

    def select_barber(self):
        handle_message(make_message(MAIN_MENU_RESERVE), self.bot)
        return handle_message(make_message(format_barber_label(self.barber)), self.bot)

    def test_selection_sends_one_photo_with_full_profile_and_inline_buttons(self):
        self.barber.image = self.image()
        self.barber.save()
        handle_message(make_message(MAIN_MENU_RESERVE), self.bot)
        self.bot.calls.clear()
        card = handle_message(make_message(format_barber_label(self.barber)), self.bot)
        self.assertEqual(len(self.bot.calls), 1)
        self.assertEqual(card['method'], 'send_photo')
        for text in ['رضا احمدی', 'فید', '9', 'سوابق حرفه‌ای']:
            self.assertIn(text, card['text'])
        self.assertEqual(card['reply_markup']['inline_keyboard'][0][0]['callback_data'], f'portfolio:{self.barber.pk}:0')

    def test_portfolio_is_on_demand_paginated_and_hides_inactive_images(self):
        BarberPortfolio.objects.create(barber=self.barber, image=self.image(), title='اول', position=1)
        BarberPortfolio.objects.create(barber=self.barber, image=self.image(), title='دوم', position=2)
        BarberPortfolio.objects.create(barber=self.barber, image=self.image(), title='پنهان', is_active=False)
        self.select_barber()
        self.bot.calls.clear()
        result = handle_callback_query(make_callback(f'portfolio:{self.barber.pk}:0'), self.bot)
        self.assertIn('اول', result['text'])
        self.assertIn('1 از 2', result['text'])
        self.assertEqual(self.bot.calls[0]['method'], 'answer_callback_query')
        result = handle_callback_query(make_callback(f'portfolio:{self.barber.pk}:1'), self.bot)
        self.assertIn('دوم', result['text'])
        self.assertNotIn('پنهان', result['text'])
        self.assertEqual(BotConversationState.objects.get().state, BotConversationState.State.WAITING_FOR_BARBER_PROFILE)

    def test_new_customer_fullname_flow_finishes_reservation(self):
        day = timezone.localdate() + timedelta(days=1)
        BarberWorkingSchedule.objects.create(barber=self.barber, day_of_week=day.isoweekday(), start_time=time(9), end_time=time(10))
        self.select_barber()
        handle_callback_query(make_callback(f'book:{self.barber.pk}'), self.bot)
        handle_message(make_message(gregorian_to_jalali(day)), self.bot)
        handle_message(make_message('09:00'), self.bot)
        self.assertEqual(BotConversationState.objects.get().state, BotConversationState.State.WAITING_FOR_FULL_NAME)
        handle_message(make_message('  محمد رضا   علی نژاد  '), self.bot)
        self.assertEqual(BotConversationState.objects.get().state, BotConversationState.State.WAITING_FOR_PHONE)
        handle_message(make_message('۰۹۱۲۳۴۵۶۷۸۹'), self.bot)
        handle_message(make_message(RESERVATION_CONFIRM_TEXT), self.bot)
        user = BotUser.objects.get()
        self.assertEqual(user.full_name, 'محمد رضا علی نژاد')
        self.assertEqual(user.appointments.count(), 1)

    def test_fullname_validation_and_menu_navigation(self):
        handle_message(make_message(MAIN_MENU_PROFILE), self.bot)
        for text in ['علی', 'علی 123', 'a' * 201, '']:
            handle_message(make_message(text), self.bot)
            self.assertEqual(BotConversationState.objects.get().state, BotConversationState.State.WAITING_FOR_FULL_NAME)
        handle_message(make_message(MAIN_MENU_CONTACT), self.bot)
        self.assertEqual(BotConversationState.objects.get().state, BotConversationState.State.IDLE)

    def test_off_switch_applies_to_messages_and_callbacks_without_changing_state(self):
        self.select_barber()
        control = BotControl.current()
        control.is_enabled = False
        control.offline_message = 'کمی بعد برمی‌گردیم'
        control.save()
        for update in [{'message': make_message('/start')}, {'callback_query': make_callback(f'book:{self.barber.pk}')}]:
            result = handle_update(update, self.bot)
            self.assertEqual(result['text'], control.offline_message)
            self.assertEqual(BotConversationState.objects.get().state, BotConversationState.State.WAITING_FOR_BARBER_PROFILE)

    def test_stale_and_other_user_callbacks_cannot_change_reservation(self):
        self.select_barber()
        handle_callback_query(make_callback(f'book:{self.barber.pk}', user_id=8001), self.bot)
        self.assertEqual(BotConversationState.objects.get(user__bale_user_id=1001).state, BotConversationState.State.WAITING_FOR_BARBER_PROFILE)
        handle_callback_query(make_callback(f'book:{self.barber.pk}:invalid'), self.bot)
        self.assertEqual(BotConversationState.objects.get(user__bale_user_id=1001).state, BotConversationState.State.WAITING_FOR_BARBER_PROFILE)
        self.assertFalse(BotUser.objects.filter(bale_user_id=9999).exists())

    def test_photo_file_id_is_cached_and_reuploaded_when_rejected(self):
        client = Mock(token='test-media-token')
        client.send_photo.return_value = {'photo': [{'file_id': 'cached-photo'}]}
        photo = Path('panel/static/panel/payizan-logo.png')
        send_image_card(client, 100, photo, 'caption')
        send_image_card(client, 100, photo, 'caption')
        self.assertEqual(client.send_photo.call_args.args[1], 'cached-photo')
        client.send_photo.side_effect = [BaleAPIError('old file'), {'photo': [{'file_id': 'new-photo'}]}]
        send_image_card(client, 100, photo, 'caption')
        self.assertTrue(client.send_photo.call_args.args[1].closed)

    def test_photo_api_encodes_multipart_markup_and_has_caption(self):
        session = FakeSession()
        client = BaleBotClient('test-token', session=session)
        keyboard = {'inline_keyboard': [[{'text': 'نمونه‌کار', 'callback_data': 'portfolio:1:0'}]]}
        with Path('panel/static/panel/payizan-logo.png').open('rb') as file:
            client.send_photo(10, file, 'پروفایل', keyboard)
        _, url, kwargs = session.calls[0]
        self.assertTrue(url.endswith('/sendPhoto'))
        self.assertEqual(json.loads(kwargs['data']['reply_markup']), keyboard)
        self.assertEqual(kwargs['data']['caption'], 'پروفایل')
