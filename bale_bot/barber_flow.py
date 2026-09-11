from appointments.models import Barber
from bale_bot.media import DEFAULT_PORTRAIT, send_image_card


def profile_keyboard(barber):
    return {'inline_keyboard': [
        [{'text': '📸 دیدن نمونه‌کارها', 'callback_data': f'portfolio:{barber.pk}:0'}],
        [{'text': '📅 انتخاب روز و ساعت', 'callback_data': f'book:{barber.pk}'}],
        [{'text': '↩️ انتخاب آرایشگر دیگر', 'callback_data': 'barbers'}],
    ]}


def show_barber_profile(client, chat_id, barber):
    lines = [f'✂️ {barber}', '']
    if barber.specialty:
        lines.append(f'🎯 تخصص: {barber.specialty}')
    if barber.experience_years:
        lines.append(f'⭐ {barber.experience_years} سال تجربه در کنار شما')
    if barber.description:
        lines.extend(['', barber.description[:700]])
    if barber.biography:
        lines.extend(['', '🌿 آشنایی بیشتر', barber.biography])
    lines.extend(['', 'سبک دلخواهت را در نمونه‌کارها پیدا کن؛ هر وقت آماده‌ای، روز و ساعتت را انتخاب کن.'])
    return send_image_card(client, chat_id, barber.image or DEFAULT_PORTRAIT, '\n'.join(lines), profile_keyboard(barber))


def show_portfolio(client, chat_id, barber_id, page=0):
    barber = Barber.objects.filter(pk=barber_id, is_active=True).first()
    if barber is None:
        return client.send_message(chat_id, '🌿 این آرایشگر فعلاً در دسترس نیست. از منوی رزرو، آرایشگر دیگری انتخاب کن.')
    works = barber.portfolio.filter(is_active=True)
    count = works.count()
    if not count:
        return client.send_message(chat_id, '📸 نمونه‌کارهای تازه به‌زودی اینجا قرار می‌گیرند.', profile_keyboard(barber))
    page = max(0, min(page, count - 1))
    work = works[page]
    buttons = []
    if page > 0:
        buttons.append({'text': 'قبلی ◀️', 'callback_data': f'portfolio:{barber.pk}:{page - 1}'})
    if page + 1 < count:
        buttons.append({'text': '▶️ بعدی', 'callback_data': f'portfolio:{barber.pk}:{page + 1}'})
    keyboard = ([buttons] if buttons else []) + [
        [{'text': '👤 پروفایل آرایشگر', 'callback_data': f'barber:{barber.pk}'}],
        [{'text': '📅 رزرو با این آرایشگر', 'callback_data': f'book:{barber.pk}'}],
    ]
    caption = f'📸 {work.title or "نمونه‌کار"}\n✂️ {barber}\n\n{work.caption}\n\n{page + 1} از {count}'
    return send_image_card(client, chat_id, work.image, caption, {'inline_keyboard': keyboard})
