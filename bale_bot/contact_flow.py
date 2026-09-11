from appointments.models import SalonSettings
from bale_bot.menu import MAIN_MENU_KEYBOARD
from bale_bot.media import DEFAULT_LOGO, send_image_card


def show_contact_info(client, chat_id):
    settings = get_salon_settings()
    if settings is None:
        settings = SalonSettings(salon_name='پیرایش تخصصی پاییزان')

    links = []
    if settings.location_url:
        links.append([{'text': '📍 مسیریابی تا سالن', 'url': settings.location_url}])
    if settings.social_url:
        links.append([{'text': '🌿 همراه ما در شبکه اجتماعی', 'url': settings.social_url}])
    markup = {'inline_keyboard': links} if links else {'keyboard': MAIN_MENU_KEYBOARD, 'resize_keyboard': True}
    return send_image_card(client, chat_id, settings.logo or DEFAULT_LOGO, format_contact_info(settings), markup)


def get_salon_settings():
    return SalonSettings.objects.order_by('id').first()


def format_contact_info(settings):
    lines = [f'🍂 {settings.salon_name}', '', settings.contact_intro or 'خوشحال می‌شویم صدایت را بشنویم! برای هماهنگی، پرسیدن سؤال یا یک سلام ساده، کنار تو هستیم. ✂️', '']
    for label, value in [('☎️ شماره تماس', settings.phone), ('📍 آدرس', settings.address), ('🕘 ساعات کاری', settings.working_hours_text)]:
        if value:
            lines.append(f'{label}: {value}')
    if not settings.phone and not settings.address:
        lines.append('راه‌های ارتباطی به‌زودی اینجا قرار می‌گیرند. برای رزرو، از دکمه «رزرو نوبت» استفاده کن.')
    lines.extend(['', 'پاییزان؛ فرصتی برای یک حال خوب 🌿'])
    return '\n'.join(lines)
