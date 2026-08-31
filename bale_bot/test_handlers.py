import os
from datetime import time, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
from django.test import TestCase
from django.utils import timezone

django.setup()

from appointments.models import Appointment, Barber, BarberWorkingSchedule, BotConversationState, BotUser, SalonSettings
from appointments.utils.date_utils import gregorian_to_jalali
from bale_bot.handlers import handle_message
from bale_bot.menu import (
    MAIN_MENU_CONTACT,
    MAIN_MENU_KEYBOARD,
    MAIN_MENU_MY_APPOINTMENTS,
    MAIN_MENU_PROFILE,
    MAIN_MENU_RESERVE,
    MAIN_MENU_TEXT,
    UNKNOWN_MESSAGE_TEXT,
)
from bale_bot.my_appointments_flow import (
    CANCEL_APPOINTMENT_NO,
    CANCEL_APPOINTMENT_YES,
    format_cancel_button,
)
from bale_bot.profile_flow import PROFILE_EDIT_TEXT
from bale_bot.reservation_flow import RESERVATION_CONFIRM_TEXT, format_barber_label


class FakeClient:
    def __init__(self):
        self.calls = []

    def send_message(self, chat_id, text, reply_markup=None):
        self.calls.append(
            {
                'method': 'send_message',
                'chat_id': chat_id,
                'text': text,
                'reply_markup': reply_markup,
            }
        )
        return self.calls[-1]

    def send_reply_keyboard(self, chat_id, text, keyboard, resize_keyboard=True, one_time_keyboard=False):
        self.calls.append(
            {
                'method': 'send_reply_keyboard',
                'chat_id': chat_id,
                'text': text,
                'keyboard': keyboard,
                'resize_keyboard': resize_keyboard,
                'one_time_keyboard': one_time_keyboard,
            }
        )
        return self.calls[-1]


def make_message(text, user_id=1001, chat_id=2002):
    return {
        'from': {'id': user_id},
        'chat': {'id': chat_id},
        'text': text,
    }


def next_weekday(weekday):
    current_date = timezone.localdate()
    days_until_weekday = (weekday - current_date.isoweekday()) % 7
    return current_date + timedelta(days=days_until_weekday)


class MainMenuHandlerTests(TestCase):
    def setUp(self):
        self.client = FakeClient()

    def test_start_sends_main_menu_keyboard_and_creates_user(self):
        result = handle_message(make_message('/start'), self.client)

        self.assertEqual(result['method'], 'send_reply_keyboard')
        self.assertEqual(result['chat_id'], 2002)
        self.assertEqual(result['text'], MAIN_MENU_TEXT)
        self.assertEqual(result['keyboard'], MAIN_MENU_KEYBOARD)
        self.assertTrue(BotUser.objects.filter(bale_user_id=1001).exists())

    def test_unknown_text_asks_user_to_choose_from_menu(self):
        result = handle_message(make_message('سلام'), self.client)

        self.assertEqual(result['method'], 'send_message')
        self.assertEqual(result['text'], UNKNOWN_MESSAGE_TEXT)

    def test_message_without_chat_id_is_ignored(self):
        result = handle_message({'from': {'id': 1001}, 'chat': {}, 'text': '/start'}, self.client)

        self.assertIsNone(result)
        self.assertEqual(self.client.calls, [])


class ProfileHandlerTests(TestCase):
    def setUp(self):
        self.client = FakeClient()

    def test_profile_option_starts_profile_completion_when_user_is_incomplete(self):
        result = handle_message(make_message(MAIN_MENU_PROFILE), self.client)
        user = BotUser.objects.get(bale_user_id=1001)

        self.assertEqual(result['text'], 'لطفا نام خود را وارد کنید.')
        self.assertEqual(user.conversation_state.state, BotConversationState.State.WAITING_FOR_FIRST_NAME)

    def test_profile_completion_saves_user_and_resets_state(self):
        handle_message(make_message(MAIN_MENU_PROFILE), self.client)
        handle_message(make_message('علی'), self.client)
        handle_message(make_message('احمدی'), self.client)
        result = handle_message(make_message('09123456789'), self.client)

        user = BotUser.objects.get(bale_user_id=1001)
        self.assertEqual(user.first_name, 'علی')
        self.assertEqual(user.last_name, 'احمدی')
        self.assertEqual(user.phone, '09123456789')
        self.assertEqual(user.conversation_state.state, BotConversationState.State.IDLE)
        self.assertEqual(result['method'], 'send_reply_keyboard')
        self.assertIn('پروفایل شما:', result['text'])
        self.assertIn(PROFILE_EDIT_TEXT, result['keyboard'][0][0]['text'])

    def test_invalid_phone_keeps_user_in_phone_step(self):
        handle_message(make_message(MAIN_MENU_PROFILE), self.client)
        handle_message(make_message('علی'), self.client)
        handle_message(make_message('احمدی'), self.client)
        result = handle_message(make_message('123'), self.client)

        user = BotUser.objects.get(bale_user_id=1001)
        self.assertEqual(user.conversation_state.state, BotConversationState.State.WAITING_FOR_PHONE)
        self.assertEqual(result['text'], 'شماره موبایل معتبر نیست. لطفا شماره را دوباره وارد کنید.')

    def test_complete_profile_is_displayed_with_edit_option(self):
        BotUser.objects.create(
            bale_user_id=1001,
            first_name='سارا',
            last_name='کریمی',
            phone='09120000000',
        )

        result = handle_message(make_message(MAIN_MENU_PROFILE), self.client)

        self.assertEqual(result['method'], 'send_reply_keyboard')
        self.assertIn('سارا', result['text'])
        self.assertIn('09120000000', result['text'])
        self.assertEqual(result['keyboard'][0][0]['text'], PROFILE_EDIT_TEXT)

    def test_edit_profile_restarts_profile_flow(self):
        BotUser.objects.create(
            bale_user_id=1001,
            first_name='سارا',
            last_name='کریمی',
            phone='09120000000',
        )

        result = handle_message(make_message(PROFILE_EDIT_TEXT), self.client)
        user = BotUser.objects.get(bale_user_id=1001)

        self.assertEqual(result['text'], 'لطفا نام خود را وارد کنید.')
        self.assertEqual(user.conversation_state.state, BotConversationState.State.WAITING_FOR_FIRST_NAME)


class ReservationHandlerTests(TestCase):
    def setUp(self):
        self.client = FakeClient()
        self.user = BotUser.objects.create(
            bale_user_id=1001,
            first_name='علی',
            last_name='احمدی',
            phone='09123456789',
        )
        self.barber = Barber.objects.create(first_name='رضا', last_name='کریمی')
        self.target_date = next_weekday(BarberWorkingSchedule.Weekday.MONDAY)
        BarberWorkingSchedule.objects.create(
            barber=self.barber,
            day_of_week=BarberWorkingSchedule.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(10, 0),
            slot_duration_minutes=30,
        )

    def test_reservation_flow_creates_booked_appointment(self):
        handle_message(make_message(MAIN_MENU_RESERVE), self.client)
        handle_message(make_message(format_barber_label(self.barber)), self.client)
        handle_message(make_message(gregorian_to_jalali(self.target_date)), self.client)
        summary = handle_message(make_message('09:00'), self.client)
        result = handle_message(make_message(RESERVATION_CONFIRM_TEXT), self.client)

        appointment = Appointment.objects.get(user=self.user, barber=self.barber)
        self.assertEqual(summary['method'], 'send_reply_keyboard')
        self.assertIn('خلاصه رزرو:', summary['text'])
        self.assertIn(gregorian_to_jalali(self.target_date), summary['text'])
        self.assertEqual(appointment.status, Appointment.Status.BOOKED)
        self.assertEqual(appointment.start_time, time(9, 0))
        self.assertEqual(result['method'], 'send_reply_keyboard')
        self.assertIn('نوبت شما با موفقیت ثبت شد.', result['text'])

    def test_last_moment_booked_slot_returns_user_to_time_selection(self):
        other_user = BotUser.objects.create(bale_user_id=1002, first_name='مینا')
        handle_message(make_message(MAIN_MENU_RESERVE), self.client)
        handle_message(make_message(format_barber_label(self.barber)), self.client)
        handle_message(make_message(gregorian_to_jalali(self.target_date)), self.client)
        handle_message(make_message('09:00'), self.client)
        Appointment.objects.create(
            user=other_user,
            barber=self.barber,
            date=self.target_date,
            start_time=time(9, 0),
            status=Appointment.Status.BOOKED,
        )

        result = handle_message(make_message(RESERVATION_CONFIRM_TEXT), self.client)
        self.user.refresh_from_db()

        self.assertIn('لحظه آخر', result['text'])
        self.assertEqual(self.user.conversation_state.state, BotConversationState.State.WAITING_FOR_TIME)
        self.assertEqual(Appointment.objects.filter(user=self.user, barber=self.barber).count(), 0)


class MyAppointmentsHandlerTests(TestCase):
    def setUp(self):
        self.client = FakeClient()
        self.user = BotUser.objects.create(
            bale_user_id=1001,
            first_name='علی',
            last_name='احمدی',
            phone='09123456789',
        )
        self.barber = Barber.objects.create(first_name='رضا', last_name='کریمی')
        self.future_date = timezone.localdate() + timedelta(days=1)
        self.appointment = Appointment.objects.create(
            user=self.user,
            barber=self.barber,
            date=self.future_date,
            start_time=time(12, 0),
            status=Appointment.Status.BOOKED,
        )

    def test_my_appointments_shows_future_appointments_with_cancel_button(self):
        result = handle_message(make_message(MAIN_MENU_MY_APPOINTMENTS), self.client)
        self.user.refresh_from_db()

        self.assertEqual(result['method'], 'send_reply_keyboard')
        self.assertIn('نوبت‌های آینده شما:', result['text'])
        self.assertIn(gregorian_to_jalali(self.future_date), result['text'])
        self.assertEqual(result['keyboard'][0][0]['text'], format_cancel_button(self.appointment))
        self.assertEqual(self.user.conversation_state.state, BotConversationState.State.WAITING_FOR_CANCEL_APPOINTMENT)

    def test_cancel_flow_requires_confirmation(self):
        handle_message(make_message(MAIN_MENU_MY_APPOINTMENTS), self.client)
        result = handle_message(make_message(format_cancel_button(self.appointment)), self.client)
        self.user.refresh_from_db()

        self.assertEqual(result['method'], 'send_reply_keyboard')
        self.assertIn('آیا مطمئن هستید؟', result['text'])
        self.assertEqual(result['keyboard'][0][0]['text'], CANCEL_APPOINTMENT_YES)
        self.assertEqual(result['keyboard'][0][1]['text'], CANCEL_APPOINTMENT_NO)
        self.assertEqual(self.user.conversation_state.state, BotConversationState.State.WAITING_FOR_CANCEL_CONFIRMATION)

    def test_cancel_yes_changes_status_without_deleting_appointment(self):
        handle_message(make_message(MAIN_MENU_MY_APPOINTMENTS), self.client)
        handle_message(make_message(format_cancel_button(self.appointment)), self.client)
        result = handle_message(make_message(CANCEL_APPOINTMENT_YES), self.client)

        self.appointment.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(result['method'], 'send_reply_keyboard')
        self.assertEqual(self.appointment.status, Appointment.Status.CANCELLED_BY_USER)
        self.assertIsNotNone(self.appointment.cancelled_at)
        self.assertTrue(Appointment.objects.filter(id=self.appointment.id).exists())
        self.assertEqual(self.user.conversation_state.state, BotConversationState.State.IDLE)

    def test_cancel_no_keeps_appointment_booked(self):
        handle_message(make_message(MAIN_MENU_MY_APPOINTMENTS), self.client)
        handle_message(make_message(format_cancel_button(self.appointment)), self.client)
        handle_message(make_message(CANCEL_APPOINTMENT_NO), self.client)

        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.BOOKED)


class ContactInfoHandlerTests(TestCase):
    def setUp(self):
        self.client = FakeClient()

    def test_contact_info_without_settings_shows_not_configured_message(self):
        result = handle_message(make_message(MAIN_MENU_CONTACT), self.client)

        self.assertEqual(result['method'], 'send_reply_keyboard')
        self.assertEqual(result['text'], 'اطلاعات ارتباط با آرایشگاه هنوز در پنل مدیریت ثبت نشده است.')
        self.assertEqual(result['keyboard'], MAIN_MENU_KEYBOARD)

    def test_contact_info_is_read_from_salon_settings(self):
        SalonSettings.objects.create(
            salon_name='آرایشگاه تست',
            phone='02112345678',
            address='تهران، خیابان تست',
            working_hours_text='شنبه تا چهارشنبه ۹ تا ۱۸',
            location_url='https://example.com/location',
        )

        result = handle_message(make_message(MAIN_MENU_CONTACT), self.client)

        self.assertEqual(result['method'], 'send_reply_keyboard')
        self.assertIn('نام آرایشگاه: آرایشگاه تست', result['text'])
        self.assertIn('شماره تماس: 02112345678', result['text'])
        self.assertIn('آدرس: تهران، خیابان تست', result['text'])
        self.assertIn('ساعات کاری: شنبه تا چهارشنبه ۹ تا ۱۸', result['text'])
        self.assertIn('لوکیشن: https://example.com/location', result['text'])
