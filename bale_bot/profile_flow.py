import re

from appointments.models import BotConversationState, BotUser
from bale_bot.menu import MAIN_MENU_KEYBOARD


PROFILE_EDIT_TEXT = 'ویرایش اطلاعات'
PROFILE_KEYBOARD = [
    [{'text': PROFILE_EDIT_TEXT}],
    *MAIN_MENU_KEYBOARD,
]


def get_or_create_bot_user(message):
    bale_user_id = get_bale_user_id(message)
    if bale_user_id is None:
        return None

    user, _ = BotUser.objects.get_or_create(bale_user_id=bale_user_id)
    BotConversationState.objects.get_or_create(user=user)
    return user


def get_bale_user_id(message):
    sender = message.get('from') or {}
    chat = message.get('chat') or {}
    return sender.get('id') or chat.get('id')


def get_user_state(user):
    state, _ = BotConversationState.objects.get_or_create(user=user)
    return state


def is_profile_complete(user):
    return bool(user.first_name and user.last_name and user.phone)


def start_profile_edit(client, chat_id, user):
    state = get_user_state(user)
    state.state = BotConversationState.State.WAITING_FOR_FIRST_NAME
    state.data = {}
    state.save(update_fields=['state', 'data', 'updated_at'])
    return client.send_message(chat_id=chat_id, text='لطفا نام خود را وارد کنید.')


def show_profile_or_start_edit(client, chat_id, user):
    if not is_profile_complete(user):
        return start_profile_edit(client, chat_id, user)

    return send_profile(client, chat_id, user)


def send_profile(client, chat_id, user):
    text = (
        'پروفایل شما:\n'
        f'نام: {user.first_name}\n'
        f'نام خانوادگی: {user.last_name}\n'
        f'شماره موبایل: {user.phone}'
    )
    return client.send_reply_keyboard(
        chat_id=chat_id,
        text=text,
        keyboard=PROFILE_KEYBOARD,
        resize_keyboard=True,
    )


def handle_profile_state(client, chat_id, user, text):
    state = get_user_state(user)

    if state.state == BotConversationState.State.WAITING_FOR_FIRST_NAME:
        return save_first_name_and_ask_last_name(client, chat_id, state, text)

    if state.state == BotConversationState.State.WAITING_FOR_LAST_NAME:
        return save_last_name_and_ask_phone(client, chat_id, state, text)

    if state.state == BotConversationState.State.WAITING_FOR_PHONE:
        return save_phone_and_finish(client, chat_id, user, state, text)

    return None


def save_first_name_and_ask_last_name(client, chat_id, state, text):
    cleaned_text = text.strip()
    if not cleaned_text:
        return client.send_message(chat_id=chat_id, text='نام نمی‌تواند خالی باشد. لطفا نام خود را وارد کنید.')

    state.data = {**state.data, 'first_name': cleaned_text}
    state.state = BotConversationState.State.WAITING_FOR_LAST_NAME
    state.save(update_fields=['state', 'data', 'updated_at'])
    return client.send_message(chat_id=chat_id, text='لطفا نام خانوادگی خود را وارد کنید.')


def save_last_name_and_ask_phone(client, chat_id, state, text):
    cleaned_text = text.strip()
    if not cleaned_text:
        return client.send_message(
            chat_id=chat_id,
            text='نام خانوادگی نمی‌تواند خالی باشد. لطفا نام خانوادگی خود را وارد کنید.',
        )

    state.data = {**state.data, 'last_name': cleaned_text}
    state.state = BotConversationState.State.WAITING_FOR_PHONE
    state.save(update_fields=['state', 'data', 'updated_at'])
    return client.send_message(chat_id=chat_id, text='لطفا شماره موبایل خود را وارد کنید.')


def save_phone_and_finish(client, chat_id, user, state, text):
    phone = normalize_phone(text)
    if not is_valid_phone(phone):
        return client.send_message(
            chat_id=chat_id,
            text='شماره موبایل معتبر نیست. لطفا شماره را دوباره وارد کنید.',
        )

    user.first_name = state.data.get('first_name', '').strip()
    user.last_name = state.data.get('last_name', '').strip()
    user.phone = phone
    user.save(update_fields=['first_name', 'last_name', 'phone', 'updated_at'])
    state.reset()

    return send_profile(client, chat_id, user)


def normalize_phone(text):
    translation = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
    return re.sub(r'[\s-]', '', text.strip().translate(translation))


def is_valid_phone(phone):
    return bool(re.fullmatch(r'(\+98|0)?9\d{9}', phone))
