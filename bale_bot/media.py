import hashlib
import logging
from pathlib import Path

from django.conf import settings
from django.core.cache import cache

from bale_bot.client import BaleAPIError

logger = logging.getLogger(__name__)
DEFAULT_LOGO = Path(settings.BASE_DIR) / 'panel/static/panel/payizan-logo.png'
DEFAULT_PORTRAIT = Path(settings.BASE_DIR) / 'panel/static/panel/barber-placeholder.png'


def send_image_card(client, chat_id, photo, caption, reply_markup=None):
    """Reuse Bale file IDs; upload directly so local media needs no public URL."""
    name = str(getattr(photo, 'name', photo))
    token = getattr(client, 'token', '')
    key = 'bale-photo:' + hashlib.sha256(f'{token}:{name}'.encode()).hexdigest()
    file_id = cache.get(key)
    if file_id:
        try:
            return client.send_photo(chat_id, file_id, caption, reply_markup)
        except BaleAPIError:
            cache.delete(key)
    try:
        with photo.open('rb') as stream:
            result = client.send_photo(chat_id, stream, caption, reply_markup)
        sizes = result.get('photo', []) if isinstance(result, dict) else []
        if sizes and isinstance(sizes[-1], dict) and sizes[-1].get('file_id'):
            cache.set(key, sizes[-1]['file_id'], 86400)
        return result
    except (OSError, ValueError, BaleAPIError):
        logger.warning('Could not send a profile image; sending its caption instead.')
        return client.send_message(chat_id=chat_id, text=caption[:4096], reply_markup=reply_markup)
