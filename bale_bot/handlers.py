import logging
import re

from appointments.models import Barber, BotConversationState
from panel.models import BotControl
from bale_bot.barber_flow import show_barber_profile, show_portfolio
from bale_bot.client import BaleAPIError
from bale_bot.utils import positive_id
from bale_bot.menu import (
    MAIN_MENU_KEYBOARD,
    MAIN_MENU_CONTACT,
    MAIN_MENU_OPTIONS,
    MAIN_MENU_MY_APPOINTMENTS,
    MAIN_MENU_PROFILE,
    MAIN_MENU_RESERVE,
    MAIN_MENU_TEXT,
    UNKNOWN_MESSAGE_TEXT,
)
from bale_bot.contact_flow import show_contact_info
from bale_bot.my_appointments_flow import (
    handle_my_appointments_state,
    is_my_appointments_state,
    show_my_appointments,
)
from bale_bot.profile_flow import (
    PROFILE_EDIT_TEXT,
    get_or_create_bot_user,
    get_user_state,
    handle_profile_state,
    show_profile_or_start_edit,
    start_profile_edit,
)
from bale_bot.reservation_flow import handle_reservation_state, is_reservation_state, send_date_selection, start_reservation

logger = logging.getLogger(__name__)


def handle_update(update, client):
    if not isinstance(update, dict):
        return None
    message = update.get('message')
    callback_query = update.get('callback_query')

    if message:
        return handle_message(message, client)

    if callback_query:
        return handle_callback_query(callback_query, client)

    return None


def handle_message(message, client):
    if not isinstance(message, dict):
        return None
    chat = message.get('chat') if isinstance(message.get('chat'), dict) else {}
    chat_id = chat.get('id')
    text = message.get('text')
    text = text.strip() if isinstance(text, str) else ''

    if not chat_id:
        return None

    control = BotControl.current()
    if not control.is_enabled:
        return client.send_message(chat_id, control.offline_message)

    user = get_or_create_bot_user(message)
    if user is None:
        return client.send_message(chat_id=chat_id, text='🌿 پیام را کامل دریافت نکردم؛ لطفاً /start را در گفتگوی خصوصی ربات بفرست.')

    if text in {'/start', '/cancel', '↩️ بازگشت به منو'}:
        get_user_state(user).reset()
        return send_main_menu(client, chat_id)

    state = get_user_state(user)
    if text in {MAIN_MENU_RESERVE, MAIN_MENU_PROFILE, MAIN_MENU_MY_APPOINTMENTS, MAIN_MENU_CONTACT}:
        state.reset()
    if is_reservation_state(state):
        return handle_reservation_state(client, chat_id, user, text)

    if is_my_appointments_state(state):
        return handle_my_appointments_state(client, chat_id, user, text)

    if state.state != BotConversationState.State.IDLE:
        return handle_profile_state(client, chat_id, user, text)

    if text == MAIN_MENU_RESERVE:
        return start_reservation(client, chat_id, user)

    if text == MAIN_MENU_PROFILE:
        return show_profile_or_start_edit(client, chat_id, user)

    if text == MAIN_MENU_MY_APPOINTMENTS:
        return show_my_appointments(client, chat_id, user)

    if text == MAIN_MENU_CONTACT:
        return show_contact_info(client, chat_id)

    if text == PROFILE_EDIT_TEXT:
        return start_profile_edit(client, chat_id, user)

    if text in MAIN_MENU_OPTIONS:
        return client.send_message(chat_id=chat_id, text=MAIN_MENU_OPTIONS[text])

    return client.send_message(chat_id=chat_id, text=UNKNOWN_MESSAGE_TEXT)


def handle_callback_query(callback_query, client):
    if not isinstance(callback_query, dict):
        return None
    message = callback_query.get('message')
    if not isinstance(message, dict):
        return None
    chat = message.get('chat') if isinstance(message.get('chat'), dict) else {}
    chat_id = chat.get('id')

    if not chat_id:
        return None
    callback_id = callback_query.get('id')
    if callback_id:
        try:
            client.answer_callback_query(callback_id)
        except BaleAPIError:
            logger.warning('Could not acknowledge a callback.')
    control = BotControl.current()
    if not control.is_enabled:
        return client.send_message(chat_id, control.offline_message)
    sender = callback_query.get('from')
    if not isinstance(sender, dict) or not positive_id(sender.get('id')):
        return None
    user = get_or_create_bot_user({'from': sender, 'chat': chat})
    data = callback_query.get('data', '')
    if not isinstance(data, str):
        return None
    if data == 'barbers':
        return start_reservation(client, chat_id, user)
    match = re.fullmatch(r'(portfolio|barber|book):([0-9]{1,18})(?::([0-9]{1,6}))?', data)
    if not match:
        return client.send_message(chat_id, '🌿 این دکمه دیگر قابل استفاده نیست. با /start منوی تازه را باز کن.')
    action, barber_id, page = match.groups()
    barber = Barber.objects.filter(pk=int(barber_id), is_active=True).first()
    if barber is None:
        return client.send_message(chat_id, '🌿 این آرایشگر فعلاً در دسترس نیست؛ از منوی رزرو گزینه دیگری انتخاب کن.')
    if action == 'portfolio':
        return show_portfolio(client, chat_id, barber.pk, int(page or 0))
    state = get_user_state(user)
    if state.data.get('barber_id') != barber.pk or state.state != BotConversationState.State.WAITING_FOR_BARBER_PROFILE:
        return client.send_message(chat_id, '🌿 برای شروع رزرو تازه، از منوی «رزرو نوبت» آرایشگرت را انتخاب کن.')
    if action == 'barber':
        return show_barber_profile(client, chat_id, barber)
    state.state = BotConversationState.State.WAITING_FOR_DATE
    state.save(update_fields=['state', 'updated_at'])
    return send_date_selection(client, chat_id, user, barber)


def send_main_menu(client, chat_id):
    return client.send_reply_keyboard(
        chat_id=chat_id,
        text=MAIN_MENU_TEXT,
        keyboard=MAIN_MENU_KEYBOARD,
        resize_keyboard=True,
    )
