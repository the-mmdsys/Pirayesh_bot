import re

from appointments.models import BotConversationState, BotUser
from bale_bot.menu import MAIN_MENU_KEYBOARD
from bale_bot.utils import positive_id


PROFILE_EDIT_TEXT = 'ویرایش اطلاعات'
FULL_NAME_PROMPT = '👋 خوشحالیم که اینجایی! نام و نام خانوادگی‌ات را یکجا بنویس؛ مثلاً «علی احمدی».'
PHONE_PROMPT = '📱 حالا شماره موبایلت را بنویس تا برای هماهنگی نوبت با تو در ارتباط باشیم؛ مثل ۰۹۱۲۳۴۵۶۷۸۹.'
INVALID_PHONE_TEXT = '📱 شماره موبایل معتبر نیست. لطفاً شماره را مثل ۰۹۱۲۳۴۵۶۷۸۹ دوباره وارد کن.'
PROFILE_KEYBOARD = [
    [{'text': PROFILE_EDIT_TEXT}],
    *MAIN_MENU_KEYBOARD,
]


def get_or_create_bot_user(message):
    bale_user_id = get_bale_user_id(message)
    if bale_user_id is None:
        return None

    user, _ = BotUser.objects.get_or_create(bale_user_id=bale_user_id)
    return user


def get_bale_user_id(message):
    sender = message.get('from') if isinstance(message.get('from'), dict) else {}
    chat = message.get('chat') if isinstance(message.get('chat'), dict) else {}
    return positive_id(sender.get('id') or chat.get('id'))


def get_user_state(user):
    state, _ = BotConversationState.objects.get_or_create(user=user)
    return state


def is_profile_complete(user):
    full_name = user.full_name or f'{user.first_name} {user.last_name}'.strip()
    return bool(clean_full_name(full_name) and is_valid_phone(normalize_phone(user.phone)))


def start_profile_edit(client, chat_id, user):
    state = get_user_state(user)
    state.state = BotConversationState.State.WAITING_FOR_FULL_NAME
    state.data = {}
    state.save(update_fields=['state', 'data', 'updated_at'])
    return client.send_reply_keyboard(chat_id, FULL_NAME_PROMPT, [[{'text': '↩️ بازگشت به منو'}]])


def show_profile_or_start_edit(client, chat_id, user):
    if not is_profile_complete(user):
        return start_profile_edit(client, chat_id, user)

    return send_profile(client, chat_id, user)


def send_profile(client, chat_id, user):
    text = (
        '👤 پروفایل شما:\n\n'
        f'🌿 نام و نام خانوادگی: {user}\n'
        f'📱 شماره موبایل: {user.phone}\n\n'
        'همه‌چیز آماده است! از منو نوبت بگیر یا اطلاعاتت را ویرایش کن.'
    )
    return client.send_reply_keyboard(
        chat_id=chat_id,
        text=text,
        keyboard=PROFILE_KEYBOARD,
        resize_keyboard=True,
    )


def handle_profile_state(client, chat_id, user, text):
    state = get_user_state(user)

    if state.state == BotConversationState.State.WAITING_FOR_FULL_NAME:
        return save_full_name_and_ask_phone(client, chat_id, state, text)

    if state.state == BotConversationState.State.WAITING_FOR_FIRST_NAME:
        return save_first_name_and_ask_last_name(client, chat_id, state, text)

    if state.state == BotConversationState.State.WAITING_FOR_LAST_NAME:
        return save_last_name_and_ask_phone(client, chat_id, state, text)

    if state.state == BotConversationState.State.WAITING_FOR_PHONE:
        return save_phone_and_finish(client, chat_id, user, state, text)

    return None


def clean_full_name(text):
    value = ' '.join(text.split())
    if not 3 <= len(value) <= 200 or len(value.split()) < 2:
        return None
    if any(not (char.isalpha() or char in " \u200c-'") for char in value):
        return None
    return value


def save_full_name_and_ask_phone(client, chat_id, state, text, key='full_name'):
    full_name = clean_full_name(text)
    if not full_name:
        return client.send_message(chat_id, '🌿 لطفاً نام و نام خانوادگی‌ات را کامل و در یک پیام بنویس؛ مثل «علی احمدی» (حداکثر ۲۰۰ نویسه).')
    state.data = {**state.data, key: full_name}
    state.state = BotConversationState.State.WAITING_FOR_PHONE
    state.save(update_fields=['state', 'data', 'updated_at'])
    return client.send_message(chat_id, PHONE_PROMPT)


def save_user_identity(user, full_name, phone):
    user.full_name = full_name
    # Keep the old fields usable by integrations; full_name preserves compound names.
    parts = full_name.split(' ', 1)
    user.first_name = parts[0][:100]
    user.last_name = (parts[1] if len(parts) > 1 else '')[:100]
    user.phone = phone
    user.save(update_fields=['full_name', 'first_name', 'last_name', 'phone', 'updated_at'])


def save_first_name_and_ask_last_name(client, chat_id, state, text):
    cleaned_text = text.strip()
    if not cleaned_text:
        return client.send_message(chat_id=chat_id, text='🌿 نامت را ننوشتی؛ لطفاً آن را برایم بفرست.')
    if len(cleaned_text) > 100:
        return client.send_message(chat_id=chat_id, text='🌿 این نام کمی طولانی است؛ لطفاً آن را در حداکثر ۱۰۰ نویسه بنویس.')

    state.data = {**state.data, 'first_name': cleaned_text}
    state.state = BotConversationState.State.WAITING_FOR_LAST_NAME
    state.save(update_fields=['state', 'data', 'updated_at'])
    return client.send_message(chat_id=chat_id, text='🌿 ممنون! حالا نام خانوادگی‌ات را بنویس.')


def save_last_name_and_ask_phone(client, chat_id, state, text):
    cleaned_text = text.strip()
    if not cleaned_text:
        return client.send_message(
            chat_id=chat_id,
            text='🌿 نام خانوادگی‌ات جا افتاده؛ لطفاً آن را هم بنویس.',
        )
    if len(cleaned_text) > 100:
        return client.send_message(chat_id=chat_id, text='🌿 نام خانوادگی را در حداکثر ۱۰۰ نویسه بنویس تا ذخیره شود.')

    state.data = {**state.data, 'last_name': cleaned_text}
    state.state = BotConversationState.State.WAITING_FOR_PHONE
    state.save(update_fields=['state', 'data', 'updated_at'])
    return client.send_message(chat_id=chat_id, text='📱 فقط شماره موبایلت مانده؛ آن را مثل ۰۹۱۲۳۴۵۶۷۸۹ بنویس.')


def save_phone_and_finish(client, chat_id, user, state, text):
    phone = normalize_phone(text)
    if not is_valid_phone(phone):
        return client.send_message(
            chat_id=chat_id,
            text=INVALID_PHONE_TEXT,
        )

    full_name = state.data.get('full_name') or f"{state.data.get('first_name', '')} {state.data.get('last_name', '')}".strip()
    if not clean_full_name(full_name):
        return start_profile_edit(client, chat_id, user)
    save_user_identity(user, full_name, phone)
    state.reset()

    return send_profile(client, chat_id, user)


def normalize_phone(text):
    translation = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
    return re.sub(r'[\s-]', '', text.strip().translate(translation))


def is_valid_phone(phone):
    return bool(re.fullmatch(r'(\+98|0)?9\d{9}', phone))
