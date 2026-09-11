import ipaddress
import logging
import secrets
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.crypto import salted_hmac

from .models import PasswordResetChallenge, RateLimitBucket

RESET_SESSION_KEY = 'panel_password_reset'
RESET_TTL = timedelta(minutes=10)
MAX_CODE_ATTEMPTS = 5


def client_ip(request):
    # Trust only the immediate peer; forwarded headers may be user controlled.
    try:
        return str(ipaddress.ip_address(request.META.get('REMOTE_ADDR', '')))
    except ValueError:
        return None


def digest(value):
    return salted_hmac('panel-security', value, algorithm='sha256').hexdigest()


def consume_limit(scope, value, limit, seconds=900):
    now = timezone.now()
    window = int(now.timestamp()) // seconds
    key = digest(f'{scope}:{value}:{window}')
    RateLimitBucket.objects.get_or_create(key=key, defaults={'expires_at': now + timedelta(seconds=seconds)})
    return bool(RateLimitBucket.objects.filter(pk=key, count__lt=limit).update(count=F('count') + 1))


def issue_reset(request, email):
    normalized = email.strip().casefold()
    ip_allowed = consume_limit('reset-ip', client_ip(request) or 'unknown', 10)
    email_allowed = consume_limit('reset-email', normalized, 3)
    if not ip_allowed or not email_allowed:
        return False
    # Ambiguous shared email addresses must never reset an arbitrary account.
    users = list(get_user_model().objects.filter(email__iexact=normalized, is_active=True, is_superuser=True)[:2])
    user = users[0] if len(users) == 1 and users[0].has_usable_password() else None
    code = f'{secrets.randbelow(1_000_000):06d}'
    with transaction.atomic():
        if user:
            # Consistent user-before-challenge locking also serializes simultaneous resends.
            user = get_user_model().objects.select_for_update().get(pk=user.pk)
            PasswordResetChallenge.objects.filter(user=user, consumed_at__isnull=True).update(consumed_at=timezone.now())
        challenge = PasswordResetChallenge.objects.create(
            user=user, code_hash=make_password(code), expires_at=timezone.now() + RESET_TTL,
            password_fingerprint=digest(user.password) if user else '',
        )
    request.session[RESET_SESSION_KEY] = str(challenge.pk)
    if user:
        try:
            sent = send_mail(
                'کد بازیابی رمز پنل پاییزان',
                f'سلام،\n\nکد تأیید بازیابی رمز پنل شما: {code}\n\nاین کد ۱۰ دقیقه اعتبار دارد و فقط یک‌بار قابل استفاده است.\nاگر این درخواست را ثبت نکرده‌اید، این پیام را نادیده بگیرید.\n\nپیرایش تخصصی پاییزان',
                settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False,
            )
            if sent != 1:
                raise RuntimeError('Email backend did not accept the message')
        except Exception:
            # Keep the public response identical; never log the code or mail contents.
            logging.getLogger('django').error('Panel password reset email could not be delivered. Check SMTP configuration.')
            challenge.consumed_at = timezone.now()
            challenge.save(update_fields=['consumed_at'])
    return True


def current_challenge(request, for_update=False):
    value = request.session.get(RESET_SESSION_KEY)
    if not value:
        return None
    query = PasswordResetChallenge.objects
    if for_update:
        query = query.select_for_update()
    try:
        challenge = query.filter(pk=value, consumed_at__isnull=True, expires_at__gt=timezone.now()).first()
    except (ValueError, TypeError, ValidationError):
        return None
    return challenge


def verify_reset_code(request, code):
    with transaction.atomic():
        challenge = current_challenge(request, for_update=True)
        if not challenge or challenge.verified_at or challenge.attempts >= MAX_CODE_ATTEMPTS:
            return False
        claimed = PasswordResetChallenge.objects.filter(
            pk=challenge.pk, attempts__lt=MAX_CODE_ATTEMPTS, verified_at__isnull=True,
        ).update(attempts=F('attempts') + 1)
        if not claimed:
            return False
        matches = check_password(code, challenge.code_hash)
        user = challenge.user
        if not matches or not user or not user.is_active or not user.is_superuser or digest(user.password) != challenge.password_fingerprint:
            return False
        challenge.verified_at = timezone.now()
        challenge.save(update_fields=['verified_at'])
        return True
