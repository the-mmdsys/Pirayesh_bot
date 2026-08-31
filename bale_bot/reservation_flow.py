import re
from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from appointments.models import Appointment, Barber, BotConversationState
from appointments.services.availability import (
    get_available_dates,
    get_available_slots,
    get_slot_end_time,
    is_slot_available,
)
from appointments.utils.date_utils import gregorian_to_jalali, jalali_to_gregorian
from appointments.utils.time_utils import is_appointment_time_in_past
from bale_bot.menu import MAIN_MENU_KEYBOARD
from bale_bot.profile_flow import is_profile_complete, is_valid_phone, normalize_phone


RESERVATION_CANCEL_TEXT = '❌ انصراف'
RESERVATION_CONFIRM_TEXT = '✅ تأیید رزرو'
RESERVATION_FLOW_KEY = 'reservation'


class SlotUnavailableError(Exception):
    pass


def start_reservation(client, chat_id, user):
    barbers = list(Barber.objects.filter(is_active=True).order_by('first_name', 'last_name'))
    if not barbers:
        get_user_state(user).reset()
        return client.send_message(chat_id=chat_id, text='فعلا آرایشگر فعالی برای رزرو وجود ندارد.')

    state = get_user_state(user)
    state.state = BotConversationState.State.WAITING_FOR_BARBER
    state.data = {'flow': RESERVATION_FLOW_KEY}
    state.save(update_fields=['state', 'data', 'updated_at'])

    return client.send_reply_keyboard(
        chat_id=chat_id,
        text='لطفا آرایشگر مورد نظر خود را انتخاب کنید.',
        keyboard=build_barber_keyboard(barbers),
        resize_keyboard=True,
    )


def handle_reservation_state(client, chat_id, user, text):
    state = get_user_state(user)

    if text == RESERVATION_CANCEL_TEXT:
        state.reset()
        return client.send_reply_keyboard(
            chat_id=chat_id,
            text='رزرو نوبت لغو شد.',
            keyboard=MAIN_MENU_KEYBOARD,
            resize_keyboard=True,
        )

    if state.state == BotConversationState.State.WAITING_FOR_BARBER:
        return handle_barber_selection(client, chat_id, user, state, text)

    if state.state == BotConversationState.State.WAITING_FOR_DATE:
        return handle_date_selection(client, chat_id, user, state, text)

    if state.state == BotConversationState.State.WAITING_FOR_TIME:
        return handle_time_selection(client, chat_id, user, state, text)

    if state.state == BotConversationState.State.WAITING_FOR_FIRST_NAME:
        return save_reservation_first_name(client, chat_id, state, text)

    if state.state == BotConversationState.State.WAITING_FOR_LAST_NAME:
        return save_reservation_last_name(client, chat_id, state, text)

    if state.state == BotConversationState.State.WAITING_FOR_PHONE:
        return save_reservation_phone_and_show_summary(client, chat_id, user, state, text)

    if state.state == BotConversationState.State.WAITING_FOR_CONFIRMATION:
        return handle_confirmation(client, chat_id, user, state, text)

    return client.send_message(chat_id=chat_id, text='مرحله رزرو مشخص نیست. لطفا /start را بفرستید.')


def handle_barber_selection(client, chat_id, user, state, text):
    barber_id = parse_barber_id(text)
    barber = Barber.objects.filter(id=barber_id, is_active=True).first()
    if barber is None:
        return client.send_message(chat_id=chat_id, text='لطفا یکی از آرایشگرهای نمایش داده شده را انتخاب کنید.')

    state.data = {
        **state.data,
        'barber_id': barber.id,
        'barber_name': str(barber),
    }
    state.state = BotConversationState.State.WAITING_FOR_DATE
    state.save(update_fields=['state', 'data', 'updated_at'])
    return send_date_selection(client, chat_id, user, barber)


def handle_date_selection(client, chat_id, user, state, text):
    selected_date = parse_jalali_date(text)
    if selected_date is None:
        return client.send_message(
            chat_id=chat_id,
            text='لطفا تاریخ را با فرمت شمسی 1405/06/08 و از دکمه‌های نمایش داده شده انتخاب کنید.',
        )

    barber = get_selected_barber(state)
    if barber is None:
        return restart_reservation(client, chat_id, user)

    available_dates = get_available_dates(barber)
    if selected_date not in available_dates:
        return client.send_message(chat_id=chat_id, text='این روز قابل رزرو نیست. لطفا یک روز دیگر انتخاب کنید.')

    state.data = {**state.data, 'date': selected_date.isoformat()}
    state.state = BotConversationState.State.WAITING_FOR_TIME
    state.save(update_fields=['state', 'data', 'updated_at'])
    return send_time_selection(client, chat_id, barber, selected_date)


def handle_time_selection(client, chat_id, user, state, text):
    selected_time = parse_time(text)
    if selected_time is None:
        return client.send_message(chat_id=chat_id, text='لطفا ساعت را از دکمه‌های نمایش داده شده انتخاب کنید.')

    barber = get_selected_barber(state)
    selected_date = get_selected_date(state)
    if barber is None or selected_date is None:
        return restart_reservation(client, chat_id, user)

    available_slots = get_available_slots(barber, selected_date)
    if is_appointment_time_in_past(selected_date, selected_time) or selected_time not in available_slots:
        if not available_slots:
            state.state = BotConversationState.State.WAITING_FOR_DATE
            state.data.pop('date', None)
            state.data.pop('start_time', None)
            state.save(update_fields=['state', 'data', 'updated_at'])
            return send_date_selection(
                client,
                chat_id,
                user,
                barber,
                message='برای این روز ساعت آزادی باقی نمانده است. لطفا روز دیگری انتخاب کنید.',
            )
        return send_time_selection(
            client,
            chat_id,
            barber,
            selected_date,
            message='این ساعت دیگر آزاد نیست. لطفا ساعت دیگری انتخاب کنید.',
        )

    state.data = {**state.data, 'start_time': selected_time.strftime('%H:%M')}

    if not is_profile_complete(user):
        state.state = BotConversationState.State.WAITING_FOR_FIRST_NAME
        state.save(update_fields=['state', 'data', 'updated_at'])
        return client.send_message(
            chat_id=chat_id,
            text='برای تکمیل رزرو، ابتدا اطلاعات پروفایل شما لازم است. لطفا نام خود را وارد کنید.',
        )

    state.state = BotConversationState.State.WAITING_FOR_CONFIRMATION
    state.save(update_fields=['state', 'data', 'updated_at'])
    return send_reservation_summary(client, chat_id, user, state)


def save_reservation_first_name(client, chat_id, state, text):
    cleaned_text = text.strip()
    if not cleaned_text:
        return client.send_message(chat_id=chat_id, text='نام نمی‌تواند خالی باشد. لطفا نام خود را وارد کنید.')

    state.data = {**state.data, 'profile_first_name': cleaned_text}
    state.state = BotConversationState.State.WAITING_FOR_LAST_NAME
    state.save(update_fields=['state', 'data', 'updated_at'])
    return client.send_message(chat_id=chat_id, text='لطفا نام خانوادگی خود را وارد کنید.')


def save_reservation_last_name(client, chat_id, state, text):
    cleaned_text = text.strip()
    if not cleaned_text:
        return client.send_message(
            chat_id=chat_id,
            text='نام خانوادگی نمی‌تواند خالی باشد. لطفا نام خانوادگی خود را وارد کنید.',
        )

    state.data = {**state.data, 'profile_last_name': cleaned_text}
    state.state = BotConversationState.State.WAITING_FOR_PHONE
    state.save(update_fields=['state', 'data', 'updated_at'])
    return client.send_message(chat_id=chat_id, text='لطفا شماره موبایل خود را وارد کنید.')


def save_reservation_phone_and_show_summary(client, chat_id, user, state, text):
    phone = normalize_phone(text)
    if not is_valid_phone(phone):
        return client.send_message(
            chat_id=chat_id,
            text='شماره موبایل معتبر نیست. لطفا شماره را دوباره وارد کنید.',
        )

    user.first_name = state.data.get('profile_first_name', '').strip()
    user.last_name = state.data.get('profile_last_name', '').strip()
    user.phone = phone
    user.save(update_fields=['first_name', 'last_name', 'phone', 'updated_at'])

    state.data = {
        key: value
        for key, value in state.data.items()
        if key not in {'profile_first_name', 'profile_last_name'}
    }
    state.state = BotConversationState.State.WAITING_FOR_CONFIRMATION
    state.save(update_fields=['state', 'data', 'updated_at'])
    return send_reservation_summary(client, chat_id, user, state)


def handle_confirmation(client, chat_id, user, state, text):
    if text != RESERVATION_CONFIRM_TEXT:
        return client.send_message(chat_id=chat_id, text='برای ثبت نهایی، لطفا تأیید رزرو را انتخاب کنید.')

    try:
        appointment = create_appointment_from_state(user, state)
    except SlotUnavailableError:
        barber = get_selected_barber(state)
        selected_date = get_selected_date(state)
        if barber and selected_date:
            if not get_available_slots(barber, selected_date):
                state.state = BotConversationState.State.WAITING_FOR_DATE
                state.data.pop('date', None)
                state.data.pop('start_time', None)
                state.save(update_fields=['state', 'data', 'updated_at'])
                return send_date_selection(
                    client,
                    chat_id,
                    user,
                    barber,
                    message='این ساعت در لحظه آخر رزرو شد و برای آن روز ساعت آزادی باقی نمانده است. لطفا روز دیگری انتخاب کنید.',
                )

            state.state = BotConversationState.State.WAITING_FOR_TIME
            state.data.pop('start_time', None)
            state.save(update_fields=['state', 'data', 'updated_at'])
            return send_time_selection(
                client,
                chat_id,
                barber,
                selected_date,
                message='این ساعت در لحظه آخر رزرو شد. لطفا ساعت دیگری انتخاب کنید.',
            )
        return restart_reservation(client, chat_id, user)

    state.reset()
    text = (
        'نوبت شما با موفقیت ثبت شد.\n'
        f'شماره نوبت: {appointment.id}\n'
        f'آرایشگر: {appointment.barber}\n'
        f'تاریخ: {gregorian_to_jalali(appointment.date)}\n'
        f'ساعت: {appointment.start_time.strftime("%H:%M")}'
    )
    return client.send_reply_keyboard(chat_id=chat_id, text=text, keyboard=MAIN_MENU_KEYBOARD, resize_keyboard=True)


def create_appointment_from_state(user, state):
    barber = get_selected_barber(state)
    selected_date = get_selected_date(state)
    selected_time = get_selected_time(state)

    if barber is None or selected_date is None or selected_time is None:
        raise SlotUnavailableError

    try:
        with transaction.atomic():
            barber = Barber.objects.select_for_update().get(id=barber.id, is_active=True)
            if not is_slot_available(barber, selected_date, selected_time):
                raise SlotUnavailableError

            return Appointment.objects.create(
                user=user,
                barber=barber,
                date=selected_date,
                start_time=selected_time,
                end_time=get_slot_end_time(barber, selected_date, selected_time),
                status=Appointment.Status.BOOKED,
            )
    except (Barber.DoesNotExist, IntegrityError, ValidationError) as error:
        raise SlotUnavailableError from error


def send_reservation_summary(client, chat_id, user, state):
    barber = get_selected_barber(state)
    selected_date = get_selected_date(state)
    selected_time = get_selected_time(state)

    if barber is None or selected_date is None or selected_time is None:
        return client.send_message(chat_id=chat_id, text='اطلاعات رزرو کامل نیست. لطفا /start را بفرستید.')

    text = (
        'خلاصه رزرو:\n'
        f'آرایشگر: {barber}\n'
        f'تاریخ: {gregorian_to_jalali(selected_date)}\n'
        f'ساعت: {selected_time.strftime("%H:%M")}\n'
        f'نام: {user.first_name} {user.last_name}\n'
        f'شماره موبایل: {user.phone}\n\n'
        'آیا رزرو را تأیید می‌کنید؟'
    )
    keyboard = [
        [{'text': RESERVATION_CONFIRM_TEXT}, {'text': RESERVATION_CANCEL_TEXT}],
    ]
    return client.send_reply_keyboard(chat_id=chat_id, text=text, keyboard=keyboard, resize_keyboard=True)


def send_date_selection(client, chat_id, user, barber, message='لطفا روز مورد نظر را انتخاب کنید.'):
    dates = get_available_dates(barber)
    if not dates:
        get_user_state(user).reset()
        return client.send_reply_keyboard(
            chat_id=chat_id,
            text='برای این آرایشگر روز قابل رزروی پیدا نشد.',
            keyboard=MAIN_MENU_KEYBOARD,
            resize_keyboard=True,
        )

    return client.send_reply_keyboard(
        chat_id=chat_id,
        text=message,
        keyboard=build_text_keyboard([gregorian_to_jalali(item) for item in dates], per_row=2, include_cancel=True),
        resize_keyboard=True,
    )


def send_time_selection(client, chat_id, barber, selected_date, message='لطفا ساعت مورد نظر را انتخاب کنید.'):
    slots = get_available_slots(barber, selected_date)
    if not slots:
        return client.send_message(chat_id=chat_id, text='برای این روز ساعت آزادی باقی نمانده است. لطفا روز دیگری انتخاب کنید.')

    return client.send_reply_keyboard(
        chat_id=chat_id,
        text=message,
        keyboard=build_text_keyboard([slot.strftime('%H:%M') for slot in slots], per_row=3, include_cancel=True),
        resize_keyboard=True,
    )


def restart_reservation(client, chat_id, user):
    get_user_state(user).reset()
    return start_reservation(client, chat_id, user)


def get_user_state(user):
    state, _ = BotConversationState.objects.get_or_create(user=user)
    return state


def get_selected_barber(state):
    barber_id = state.data.get('barber_id')
    if not barber_id:
        return None
    return Barber.objects.filter(id=barber_id, is_active=True).first()


def get_selected_date(state):
    return parse_stored_date(state.data.get('date', ''))


def get_selected_time(state):
    return parse_time(state.data.get('start_time', ''))


def build_barber_keyboard(barbers):
    labels = [format_barber_label(barber) for barber in barbers]
    return build_text_keyboard(labels, per_row=1, include_cancel=True)


def build_text_keyboard(labels, per_row=2, include_cancel=False):
    rows = []
    for index in range(0, len(labels), per_row):
        rows.append([{'text': label} for label in labels[index:index + per_row]])
    if include_cancel:
        rows.append([{'text': RESERVATION_CANCEL_TEXT}])
    return rows


def format_barber_label(barber):
    return f'{barber} #{barber.id}'


def parse_barber_id(text):
    match = re.search(r'#(\d+)\s*$', text or '')
    if not match:
        return None
    return int(match.group(1))


def parse_jalali_date(text):
    try:
        return jalali_to_gregorian(text)
    except ValidationError:
        return None


def parse_stored_date(text):
    try:
        return datetime.strptime(text, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def parse_time(text):
    try:
        return datetime.strptime(text, '%H:%M').time()
    except (TypeError, ValueError):
        return None


def is_reservation_state(state):
    return (
        state.state
        in {
            BotConversationState.State.WAITING_FOR_BARBER,
            BotConversationState.State.WAITING_FOR_DATE,
            BotConversationState.State.WAITING_FOR_TIME,
            BotConversationState.State.WAITING_FOR_CONFIRMATION,
        }
        or state.data.get('flow') == RESERVATION_FLOW_KEY
    )
