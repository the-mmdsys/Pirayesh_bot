import re

from django.db.models import Q
from django.utils import timezone

from appointments.models import Appointment, BotConversationState
from appointments.utils.date_utils import gregorian_to_jalali
from bale_bot.menu import MAIN_MENU_KEYBOARD


CANCEL_APPOINTMENT_PREFIX = 'لغو نوبت'
CANCEL_APPOINTMENT_YES = 'بله، لغو شود'
CANCEL_APPOINTMENT_NO = 'خیر'
BACK_TO_MAIN_MENU = 'بازگشت به منو'
MY_APPOINTMENTS_FLOW_KEY = 'my_appointments'


def show_my_appointments(client, chat_id, user):
    appointments = list(get_future_appointments(user))
    state = get_user_state(user)

    if not appointments:
        state.reset()
        return client.send_reply_keyboard(
            chat_id=chat_id,
            text='شما نوبت آینده‌ای ندارید.',
            keyboard=MAIN_MENU_KEYBOARD,
            resize_keyboard=True,
        )

    state.state = BotConversationState.State.WAITING_FOR_CANCEL_APPOINTMENT
    state.data = {'flow': MY_APPOINTMENTS_FLOW_KEY}
    state.save(update_fields=['state', 'data', 'updated_at'])

    return client.send_reply_keyboard(
        chat_id=chat_id,
        text=format_appointments_list(appointments),
        keyboard=build_appointments_keyboard(appointments),
        resize_keyboard=True,
    )


def handle_my_appointments_state(client, chat_id, user, text):
    state = get_user_state(user)

    if text == BACK_TO_MAIN_MENU:
        state.reset()
        return client.send_reply_keyboard(
            chat_id=chat_id,
            text='به منوی اصلی برگشتید.',
            keyboard=MAIN_MENU_KEYBOARD,
            resize_keyboard=True,
        )

    if state.state == BotConversationState.State.WAITING_FOR_CANCEL_APPOINTMENT:
        return ask_cancel_confirmation(client, chat_id, user, state, text)

    if state.state == BotConversationState.State.WAITING_FOR_CANCEL_CONFIRMATION:
        return handle_cancel_confirmation(client, chat_id, user, state, text)

    return client.send_message(chat_id=chat_id, text='مرحله نوبت‌های من مشخص نیست. لطفا /start را بفرستید.')


def ask_cancel_confirmation(client, chat_id, user, state, text):
    appointment_id = parse_cancel_appointment_id(text)
    if appointment_id is None:
        return client.send_message(chat_id=chat_id, text='لطفا یکی از دکمه‌های لغو نوبت را انتخاب کنید.')

    appointment = get_cancellable_appointment(user, appointment_id)
    if appointment is None:
        return client.send_message(chat_id=chat_id, text='این نوبت برای لغو پیدا نشد یا دیگر قابل لغو نیست.')

    state.state = BotConversationState.State.WAITING_FOR_CANCEL_CONFIRMATION
    state.data = {
        'flow': MY_APPOINTMENTS_FLOW_KEY,
        'appointment_id': appointment.id,
    }
    state.save(update_fields=['state', 'data', 'updated_at'])

    text = (
        'آیا مطمئن هستید؟\n'
        f'آرایشگر: {appointment.barber}\n'
        f'تاریخ: {gregorian_to_jalali(appointment.date)}\n'
        f'ساعت: {appointment.start_time.strftime("%H:%M")}'
    )
    keyboard = [
        [{'text': CANCEL_APPOINTMENT_YES}, {'text': CANCEL_APPOINTMENT_NO}],
    ]
    return client.send_reply_keyboard(chat_id=chat_id, text=text, keyboard=keyboard, resize_keyboard=True)


def handle_cancel_confirmation(client, chat_id, user, state, text):
    if text == CANCEL_APPOINTMENT_NO:
        state.reset()
        return client.send_reply_keyboard(
            chat_id=chat_id,
            text='لغو نوبت انجام نشد.',
            keyboard=MAIN_MENU_KEYBOARD,
            resize_keyboard=True,
        )

    if text != CANCEL_APPOINTMENT_YES:
        return client.send_message(chat_id=chat_id, text='لطفا یکی از گزینه‌های بله یا خیر را انتخاب کنید.')

    appointment = get_cancellable_appointment(user, state.data.get('appointment_id'))
    if appointment is None:
        state.reset()
        return client.send_reply_keyboard(
            chat_id=chat_id,
            text='این نوبت دیگر قابل لغو نیست.',
            keyboard=MAIN_MENU_KEYBOARD,
            resize_keyboard=True,
        )

    appointment.status = Appointment.Status.CANCELLED_BY_USER
    appointment.cancelled_at = timezone.now()
    appointment.save()
    state.reset()

    return client.send_reply_keyboard(
        chat_id=chat_id,
        text='نوبت شما لغو شد.',
        keyboard=MAIN_MENU_KEYBOARD,
        resize_keyboard=True,
    )


def get_future_appointments(user):
    today = timezone.localdate()
    current_time = timezone.localtime().time()
    return (
        Appointment.objects.filter(user=user)
        .filter(Q(date__gt=today) | Q(date=today, start_time__gte=current_time))
        .exclude(status__in=[Appointment.Status.CANCELLED_BY_USER, Appointment.Status.CANCELLED_BY_ADMIN])
        .select_related('barber')
        .order_by('date', 'start_time')
    )


def get_cancellable_appointment(user, appointment_id):
    if not appointment_id:
        return None

    return get_future_appointments(user).filter(
        id=appointment_id,
        status=Appointment.Status.BOOKED,
    ).first()


def format_appointments_list(appointments):
    lines = ['نوبت‌های آینده شما:']

    for index, appointment in enumerate(appointments, start=1):
        lines.extend(
            [
                '',
                f'{index}. آرایشگر: {appointment.barber}',
                f'تاریخ: {gregorian_to_jalali(appointment.date)}',
                f'ساعت: {appointment.start_time.strftime("%H:%M")}',
                f'وضعیت: {appointment.get_status_display()}',
            ]
        )

    lines.append('')
    lines.append('برای لغو، دکمه نوبت مورد نظر را انتخاب کنید.')
    return '\n'.join(lines)


def build_appointments_keyboard(appointments):
    rows = [
        [{'text': format_cancel_button(appointment)}]
        for appointment in appointments
        if appointment.status == Appointment.Status.BOOKED
    ]
    rows.append([{'text': BACK_TO_MAIN_MENU}])
    return rows


def format_cancel_button(appointment):
    return f'{CANCEL_APPOINTMENT_PREFIX} #{appointment.id}'


def parse_cancel_appointment_id(text):
    match = re.search(r'#(\d+)\s*$', text or '')
    if not match:
        return None
    return int(match.group(1))


def get_user_state(user):
    state, _ = BotConversationState.objects.get_or_create(user=user)
    return state


def is_my_appointments_state(state):
    return (
        state.state
        in {
            BotConversationState.State.WAITING_FOR_CANCEL_APPOINTMENT,
            BotConversationState.State.WAITING_FOR_CANCEL_CONFIRMATION,
        }
        or state.data.get('flow') == MY_APPOINTMENTS_FLOW_KEY
    )
