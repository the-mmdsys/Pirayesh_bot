from datetime import timedelta

from django.contrib.sessions.models import Session
from django.utils import timezone

from .models import PanelSession
from .security import client_ip


class PanelSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (request.path.startswith('/panel/') and request.user.is_authenticated
                and request.user.is_staff and request.session.session_key and response.status_code < 500):
            key = request.session.session_key
            if Session.objects.filter(pk=key).exists():
                now = timezone.now()
                item, created = PanelSession.objects.get_or_create(session_id=key, defaults={
                    'user': request.user, 'ip_address': client_ip(request),
                    'user_agent': request.META.get('HTTP_USER_AGENT', '')[:400],
                })
                if not created and item.last_seen < now - timedelta(minutes=1):
                    PanelSession.objects.filter(pk=item.pk).update(last_seen=now)
        return response
