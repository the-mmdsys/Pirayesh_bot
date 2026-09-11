import uuid

from django.conf import settings
from django.db import models


class PanelSession(models.Model):
    session = models.OneToOneField('sessions.Session', on_delete=models.CASCADE, related_name='panel_details')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-last_seen']


class PasswordResetChallenge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.CASCADE)
    code_hash = models.CharField(max_length=128)
    password_fingerprint = models.CharField(max_length=64, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    verified_at = models.DateTimeField(null=True)
    consumed_at = models.DateTimeField(null=True)


class RateLimitBucket(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)


class BotControl(models.Model):
    # One shared switch for polling and webhook workers.
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    is_enabled = models.BooleanField(default=True)
    offline_message = models.CharField(
        max_length=500, default='🍂 کمی به خودمان فرصت رسیدگی می‌دهیم! به‌زودی دوباره در کنار شما هستیم. ممنون از همراهی‌تان.',
        verbose_name='پیام زمان خاموش بودن ربات',
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    transport = models.CharField(max_length=12, blank=True)

    @classmethod
    def current(cls):
        return cls.objects.get_or_create(pk=1)[0]


class MaintenanceJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = 'queued', 'در صف اجرا'
        RUNNING = 'running', 'در حال اجرا'
        SUCCEEDED = 'succeeded', 'انجام شد'
        FAILED = 'failed', 'نیاز به بررسی'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    upgrade_packages = models.BooleanField(default=False)
    # Finished jobs use NULL; the unique True value prevents concurrent upgrades.
    active = models.BooleanField(null=True, default=True, unique=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED)
    summary = models.TextField(blank=True)
    restart_required = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ['-created_at']
