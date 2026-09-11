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
from appointments.utils.date_utils import gregorian_to_jalali, jalali_to_gregorian, normalize_date_digits
from appointments.utils.time_utils import is_appointment_time_in_past
from bale_bot.menu import MAIN_MENU_KEYBOARD
from bale_bot.barber_flow import show_barber_profile
from bale_bot.profile_flow import (
    FULL_NAME_PROMPT, INVALID_PHONE_TEXT, clean_full_name, is_profile_complete,
    is_valid_phone, normalize_phone, save_full_name_and_ask_phone, save_user_identity,
)
from bale_bot.utils import positive_id, selection_id


RESERVATION_CANCEL_TEXT = '❌ انصراف'
RESERVATION_CONFIRM_TEXT = '✅ تأیید رزرو'
RESERVATION_FLOW_KEY = 'reservation'


class SlotUnavailableError(Exception):
    pass


def start_reservation(client, chat_id, user):
    barbers = list(Barber.objects.filter(is_active=True).order_by('first_name', 'last_name'))
    if not barbers:
        get_user_state(user).reset()
        return client.send_message(chat_id=chat_id, text='🌿 فعلاً آرایشگری برای رزرو آماده نیست. کمی بعد دوباره سر بزن یا از «ارتباط با ما» با سالن هماهنگ کن.')

    state = get_user_state(user)
    state.state = BotConversationState.State.WAITING_FOR_BARBER
    state.data = {'flow': RESERVATION_FLOW_KEY}
    state.save(update_fields=['state', 'data', 'updated_at'])

    return client.send_reply_keyboard(
        chat_id=chat_id,
        text='✂️ دوست داری مهمان کدام آرایشگر باشی؟\nروی نام هر کدام بزن تا با تخصص و نمونه‌کارهایش آشنا شوی.',
        keyboard=build_barber_keyboard(barbers),
        resize_keyboard=True,
    )


def handle_reservation_state(client, chat_id, user, text):
    state = get_user_state(user)

    if text == RESERVATION_CANCEL_TEXT:
        state.reset()
        return client.send_reply_keyboard(
            chat_id=chat_id,
            text='🌿 از این رزرو منصرف شدی و نوبتی ثبت نشد. هر وقت آماده بودی، دوباره شروع می‌کنیم.',
            keyboard=MAIN_MENU_KEYBOARD,
            resize_keyboard=True,
        )

    if state.state == BotConversationState.State.WAITING_FOR_BARBER:
        return handle_barber_selection(client, chat_id, user, state, text)

    if state.state == BotConversationState.State.WAITING_FOR_BARBER_PROFILE:
        if parse_barber_id(text):
            return handle_barber_selection(client, chat_id, user, state, text)
        return client.send_message(chat_id, '📸 نمونه‌کارها و دکمه انتخاب روز و ساعت زیر عکس آرایشگرت هستند. برای ادامه روی آن‌ها بزن.')

    if state.state == BotConversationState.State.WAITING_FOR_FULL_NAME:
        return save_full_name_and_ask_phone(client, chat_id, state, text, key='profile_full_name')

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

    return client.send_message(chat_id=chat_id, text='🌿 بیایید رزرو را از نو شروع کنیم؛ /start را بفرست تا راهنمایی‌ات کنم.')


def handle_barber_selection(client, chat_id, user, state, text):
    barber_id = parse_barber_id(text)
    barber = Barber.objects.filter(id=barber_id, is_active=True).first()
    if barber is None:
        return client.send_message(chat_id=chat_id, text='✂️ برای دیدن پروفایل، روی نام یکی از آرایشگرهای همین فهرست بزن.')

    state.data = {
        **state.data,
        'barber_id': barber.id,
        'barber_name': str(barber),
    }
    state.state = BotConversationState.State.WAITING_FOR_BARBER_PROFILE
    state.save(update_fields=['state', 'data', 'updated_at'])
    return show_barber_profile(client, chat_id, barber)


def handle_date_selection(client, chat_id, user, state, text):
    selected_date = parse_jalali_date(text)
    if selected_date is None:
        return client.send_message(
            chat_id=chat_id,
            text='📅 روز دلخواهت را از دکمه‌های پایین انتخاب کن. اگر تایپ می‌کنی، تاریخ شمسی را مثل ۱۴۰۵/۰۶/۰۸ بنویس.',
        )

    barber = get_selected_barber(state)
    if barber is None:
        return restart_reservation(client, chat_id, user)

    available_dates = get_available_dates(barber)
    if selected_date not in available_dates:
        return client.send_message(chat_id=chat_id, text='📅 این روز قابل رزرو نیست. یکی از روزهای آزاد فهرست را انتخاب کن تا ساعت‌ها را ببینیم.')

    state.data = {**state.data, 'date': selected_date.isoformat()}
    state.state = BotConversationState.State.WAITING_FOR_TIME
    state.save(update_fields=['state', 'data', 'updated_at'])
    return send_time_selection(client, chat_id, barber, selected_date)


def handle_time_selection(client, chat_id, user, state, text):
    selected_time = parse_time(text)
    if selected_time is None:
        return client.send_message(chat_id=chat_id, text='🕘 کدام ساعت برایت راحت‌تر است؟ روی یکی از ساعت‌های پایین بزن.')

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
                message='🌿 ساعت‌های این روز پر شده‌اند. یک روز دیگر انتخاب کن تا زمان مناسب‌تری پیدا کنیم.',
            )
        return send_time_selection(
            client,
            chat_id,
            barber,
            selected_date,
            message='🌿 این ساعت دیگر آزاد نیست. از ساعت‌های تازه، زمان دیگری انتخاب کن.',
        )

    state.data = {**state.data, 'start_time': selected_time.strftime('%H:%M')}

    if not is_profile_complete(user):
        state.state = BotConversationState.State.WAITING_FOR_FULL_NAME
        state.save(update_fields=['state', 'data', 'updated_at'])
        return client.send_reply_keyboard(
            chat_id=chat_id,
            text='🌿 فقط دو قدم تا تکمیل مشخصاتت مانده.\n' + FULL_NAME_PROMPT,
            keyboard=[[{'text': RESERVATION_CANCEL_TEXT}]],
        )

    state.state = BotConversationState.State.WAITING_FOR_CONFIRMATION
    state.save(update_fields=['state', 'data', 'updated_at'])
    return send_reservation_summary(client, chat_id, user, state)


def save_reservation_first_name(client, chat_id, state, text):
    cleaned_text = text.strip()
    if not cleaned_text:
        return client.send_message(chat_id=chat_id, text='🌿 نامت را ننوشتی؛ لطفاً آن را برایم بفرست.')
    if len(cleaned_text) > 100:
        return client.send_message(chat_id=chat_id, text='🌿 این نام کمی طولانی است؛ لطفاً آن را در حداکثر ۱۰۰ نویسه بنویس.')

    state.data = {**state.data, 'profile_first_name': cleaned_text}
    state.state = BotConversationState.State.WAITING_FOR_LAST_NAME
    state.save(update_fields=['state', 'data', 'updated_at'])
    return client.send_message(chat_id=chat_id, text='🌿 ممنون! حالا نام خانوادگی‌ات را بنویس.')


def save_reservation_last_name(client, chat_id, state, text):
    cleaned_text = text.strip()
    if not cleaned_text:
        return client.send_message(
            chat_id=chat_id,
            text='🌿 نام خانوادگی‌ات جا افتاده؛ لطفاً آن را هم بنویس.',
        )
    if len(cleaned_text) > 100:
        return client.send_message(chat_id=chat_id, text='🌿 نام خانوادگی را در حداکثر ۱۰۰ نویسه بنویس تا ذخیره شود.')

    state.data = {**state.data, 'profile_last_name': cleaned_text}
    state.state = BotConversationState.State.WAITING_FOR_PHONE
    state.save(update_fields=['state', 'data', 'updated_at'])
    return client.send_message(chat_id=chat_id, text='📱 فقط شماره موبایلت مانده؛ آن را مثل ۰۹۱۲۳۴۵۶۷۸۹ بنویس.')


def save_reservation_phone_and_show_summary(client, chat_id, user, state, text):
    phone = normalize_phone(text)
    if not is_valid_phone(phone):
        return client.send_message(
            chat_id=chat_id,
            text=INVALID_PHONE_TEXT,
        )

    full_name = state.data.get('profile_full_name') or f"{state.data.get('profile_first_name', '')} {state.data.get('profile_last_name', '')}".strip()
    if not clean_full_name(full_name):
        state.state = BotConversationState.State.WAITING_FOR_FULL_NAME
        state.save(update_fields=['state', 'updated_at'])
        return client.send_message(chat_id, FULL_NAME_PROMPT)
    save_user_identity(user, full_name, phone)

    state.data = {
        key: value
        for key, value in state.data.items()
        if key not in {'profile_first_name', 'profile_last_name', 'profile_full_name'}
    }
    state.state = BotConversationState.State.WAITING_FOR_CONFIRMATION
    state.save(update_fields=['state', 'data', 'updated_at'])
    return send_reservation_summary(client, chat_id, user, state)


def handle_confirmation(client, chat_id, user, state, text):
    if text != RESERVATION_CONFIRM_TEXT:
        return client.send_message(chat_id=chat_id, text='✨ یک قدم تا نهایی شدن نوبت مانده؛ روی «تأیید رزرو» بزن.')

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
                    message='🌿 این ساعت در لحظه آخر رزرو شد و ساعت‌های آن روز پر شدند. یک روز دیگر انتخاب کن تا دوباره زمان مناسب پیدا کنیم.',
                )

            state.state = BotConversationState.State.WAITING_FOR_TIME
            state.data.pop('start_time', None)
            state.save(update_fields=['state', 'data', 'updated_at'])
            return send_time_selection(
                client,
                chat_id,
                barber,
                selected_date,
                message='🌿 این ساعت در لحظه آخر رزرو شد. از فهرست تازه، ساعت دیگری انتخاب کن.',
            )
        return restart_reservation(client, chat_id, user)

    state.reset()
    text = (
        '✅ نوبت شما با موفقیت ثبت شد. منتظر دیدارت هستیم!\n\n'
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
        return client.send_message(chat_id=chat_id, text='🌿 بخشی از اطلاعات رزرو جا افتاده؛ با /start دوباره شروع کنیم.')

    text = (
        '🧾 یک نگاه به خلاصه رزرو بینداز:\n\n'
        f'آرایشگر: {barber}\n'
        f'تاریخ: {gregorian_to_jalali(selected_date)}\n'
        f'ساعت: {selected_time.strftime("%H:%M")}\n'
        f'نام و نام خانوادگی: {user}\n'
        f'شماره موبایل: {user.phone}\n\n'
        'همه‌چیز درست است؟ با «تأیید رزرو» نوبتت نهایی می‌شود. ✨'
    )
    keyboard = [
        [{'text': RESERVATION_CONFIRM_TEXT}, {'text': RESERVATION_CANCEL_TEXT}],
    ]
    return client.send_reply_keyboard(chat_id=chat_id, text=text, keyboard=keyboard, resize_keyboard=True)


def send_date_selection(client, chat_id, user, barber, message='📅 چه روزی منتظرت باشیم؟ یکی از روزهای آزاد پایین را انتخاب کن.'):
    dates = get_available_dates(barber)
    if not dates:
        get_user_state(user).reset()
        return client.send_reply_keyboard(
            chat_id=chat_id,
            text='🌿 فعلاً روز آزادی برای این آرایشگر نداریم. می‌توانی آرایشگر دیگری انتخاب کنی یا از «ارتباط با ما» با سالن هماهنگ شوی.',
            keyboard=MAIN_MENU_KEYBOARD,
            resize_keyboard=True,
        )

    return client.send_reply_keyboard(
        chat_id=chat_id,
        text=message,
        keyboard=build_text_keyboard([gregorian_to_jalali(item) for item in dates], per_row=2, include_cancel=True),
        resize_keyboard=True,
    )


def send_time_selection(client, chat_id, barber, selected_date, message='🕘 حالا ساعت مناسب خودت را انتخاب کن؛ این زمان‌ها هنوز آزادند.'):
    slots = get_available_slots(barber, selected_date)
    if not slots:
        return client.send_message(chat_id=chat_id, text='🌿 ساعت‌های این روز پر شده‌اند؛ یک روز دیگر را امتحان کن.')

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
    barber_id = positive_id(state.data.get('barber_id'))
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
    return selection_id(text)


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
        return datetime.strptime(normalize_date_digits(text.strip()), '%H:%M').time()
    except (AttributeError, TypeError, ValueError):
        return None


def is_reservation_state(state):
    return (
        state.state
        in {
            BotConversationState.State.WAITING_FOR_BARBER,
            BotConversationState.State.WAITING_FOR_BARBER_PROFILE,
            BotConversationState.State.WAITING_FOR_DATE,
            BotConversationState.State.WAITING_FOR_TIME,
            BotConversationState.State.WAITING_FOR_CONFIRMATION,
        }
        or state.data.get('flow') == RESERVATION_FLOW_KEY
    )
