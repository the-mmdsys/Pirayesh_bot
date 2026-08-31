from appointments.models import SalonSettings
from bale_bot.menu import MAIN_MENU_KEYBOARD


def show_contact_info(client, chat_id):
    settings = get_salon_settings()
    if settings is None:
        return client.send_reply_keyboard(
            chat_id=chat_id,
            text='اطلاعات ارتباط با آرایشگاه هنوز در پنل مدیریت ثبت نشده است.',
            keyboard=MAIN_MENU_KEYBOARD,
            resize_keyboard=True,
        )

    return client.send_reply_keyboard(
        chat_id=chat_id,
        text=format_contact_info(settings),
        keyboard=MAIN_MENU_KEYBOARD,
        resize_keyboard=True,
    )


def get_salon_settings():
    return SalonSettings.objects.order_by('id').first()


def format_contact_info(settings):
    return '\n'.join(
        [
            'اطلاعات تماس:',
            f'نام آرایشگاه: {settings.salon_name}',
            f'شماره تماس: {settings.phone or "ثبت نشده"}',
            f'آدرس: {settings.address or "ثبت نشده"}',
            f'ساعات کاری: {settings.working_hours_text or "ثبت نشده"}',
            f'لوکیشن: {settings.location_url or "ثبت نشده"}',
        ]
    )
