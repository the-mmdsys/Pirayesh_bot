from appointments.models import BotConversationState
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
from bale_bot.reservation_flow import handle_reservation_state, is_reservation_state, start_reservation


def handle_update(update, client):
    message = update.get('message')
    callback_query = update.get('callback_query')

    if message:
        return handle_message(message, client)

    if callback_query:
        return handle_callback_query(callback_query, client)

    return None


def handle_message(message, client):
    chat = message.get('chat') or {}
    chat_id = chat.get('id')
    text = (message.get('text') or '').strip()

    if not chat_id:
        return None

    user = get_or_create_bot_user(message)
    if user is None:
        return client.send_message(chat_id=chat_id, text='شناسه کاربر دریافت نشد. لطفا دوباره تلاش کنید.')

    if text == '/start':
        get_user_state(user).reset()
        return send_main_menu(client, chat_id)

    state = get_user_state(user)
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
    message = callback_query.get('message') or {}
    chat = message.get('chat') or {}
    chat_id = chat.get('id')

    if not chat_id:
        return None

    return client.send_message(
        chat_id=chat_id,
        text='درخواست شما دریافت شد.',
    )


def send_main_menu(client, chat_id):
    return client.send_reply_keyboard(
        chat_id=chat_id,
        text=MAIN_MENU_TEXT,
        keyboard=MAIN_MENU_KEYBOARD,
        resize_keyboard=True,
    )
