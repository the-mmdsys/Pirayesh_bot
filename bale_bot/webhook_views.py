import json
import logging
import os

from django.http import HttpResponseForbidden, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from bale_bot.client import BaleBotClient
from bale_bot.handlers import handle_update


logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def webhook(request):
    expected_secret = os.getenv('BALE_WEBHOOK_SECRET')
    if expected_secret:
        received_secret = request.headers.get('X-Bale-Webhook-Secret')
        if received_secret != expected_secret:
            logger.warning('Rejected Bale webhook request with invalid secret header.')
            return HttpResponseForbidden('Forbidden')

    try:
        update = json.loads(request.body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.warning('Rejected Bale webhook request with invalid JSON.')
        return JsonResponse({'status': 'invalid_json'}, status=400)

    if not isinstance(update, dict):
        return JsonResponse({'status': 'invalid_update'}, status=400)

    try:
        handle_update(update, BaleBotClient.from_env())
    except Exception:
        logger.exception('Bale webhook processing failed.')
        return JsonResponse({'status': 'error'}, status=500)

    return JsonResponse({'status': 'ok'})
