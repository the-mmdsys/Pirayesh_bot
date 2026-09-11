from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.sessions.models import Session
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from appointments.models import BotConversationState
from .auth import staff_member_required
from .forms import PanelSetPasswordForm, RecoveryEmailForm, ResetCodeForm, ResetEmailForm
from .models import PanelSession, PasswordResetChallenge
from .security import RESET_SESSION_KEY, current_challenge, digest, issue_reset, verify_reset_code
from .control_views import superuser_required


@superuser_required
@never_cache
@sensitive_post_parameters('current_password')
def recovery_email(request):
    form = RecoveryEmailForm(request.user, request.POST if request.method == 'POST' else None, initial={'email': request.user.email})
    if request.method == 'POST' and form.is_valid():
        request.user.email = form.cleaned_data['email']
        request.user.save(update_fields=['email'])
        PasswordResetChallenge.objects.filter(user=request.user, consumed_at__isnull=True).update(consumed_at=timezone.now())
        messages.success(request, 'ایمیل بازیابی رمز حساب شما ذخیره شد.')
        return redirect('panel:recovery_email')
    return render(request, 'panel/form.html', {'title': 'ایمیل بازیابی حساب مدیر', 'form': form, 'cancel_url': 'panel:dashboard'})


@never_cache
def password_reset_request(request):
    form = ResetEmailForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        if issue_reset(request, form.cleaned_data['email']):
            return redirect('panel:password_reset_verify')
        form.add_error(None, 'چند بار درخواست ارسال کد ثبت شده است؛ ۱۵ دقیقه دیگر دوباره تلاش کنید.')
    return render(request, 'panel/password_reset.html', {'title': 'بازیابی رمز عبور', 'form': form, 'step': 1})


@never_cache
@sensitive_post_parameters('code')
def password_reset_verify(request):
    challenge = current_challenge(request)
    if challenge and challenge.verified_at:
        return redirect('panel:password_reset_confirm')
    if not request.session.get(RESET_SESSION_KEY):
        return redirect('panel:password_reset')
    form = ResetCodeForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        if verify_reset_code(request, form.cleaned_data['code']):
            return redirect('panel:password_reset_confirm')
        form.add_error('code', 'کد درست نیست، منقضی شده یا تعداد تلاش‌ها تمام شده است. کد تازه درخواست کنید.')
    return render(request, 'panel/password_reset.html', {'title': 'تأیید ایمیل', 'form': form, 'step': 2})


@never_cache
@sensitive_post_parameters('new_password1', 'new_password2')
def password_reset_confirm(request):
    with transaction.atomic():
        challenge = current_challenge(request)
        if not challenge or not challenge.verified_at or not challenge.user_id:
            return redirect('panel:password_reset')
        user = get_user_model().objects.select_for_update().filter(pk=challenge.user_id).first()
        challenge = current_challenge(request, for_update=True)
        if not user or not challenge or not challenge.verified_at:
            return redirect('panel:password_reset')
        if not user.is_active or not user.is_superuser or digest(user.password) != challenge.password_fingerprint:
            return redirect('panel:password_reset')
        form = PanelSetPasswordForm(user, request.POST if request.method == 'POST' else None)
        if request.method == 'POST' and form.is_valid():
            form.save()
            PasswordResetChallenge.objects.filter(user=user, consumed_at__isnull=True).update(consumed_at=timezone.now())
            Session.objects.filter(panel_details__user=user).delete()
            logout(request)
            messages.success(request, 'رمز تازه ذخیره شد. حالا با رمز جدید وارد شوید؛ نشست‌های قبلی بسته شدند.')
            return redirect('panel:login')
    return render(request, 'panel/password_reset.html', {'title': 'تعیین رمز جدید', 'form': form, 'step': 3})


@staff_member_required
@never_cache
def sessions_list(request):
    # Include sessions created before tracking was added, without inventing IP/device data.
    unknown = Session.objects.filter(expire_date__gt=timezone.now(), panel_details__isnull=True)
    for session in unknown.iterator():
        data = session.get_decoded()
        user_id = data.get('_auth_user_id')
        if not user_id:
            continue
        users = get_user_model().objects.filter(pk=user_id, is_active=True, is_staff=True)
        if not request.user.is_superuser:
            users = users.filter(pk=request.user.pk)
        user = users.first()
        if user and data.get('_auth_user_hash') == user.get_session_auth_hash():
            PanelSession.objects.get_or_create(session=session, defaults={'user': user})
    sessions = PanelSession.objects.select_related('user', 'session').filter(session__expire_date__gt=timezone.now())
    if not request.user.is_superuser:
        sessions = sessions.filter(user=request.user)
    conversations = None
    if request.user.is_superuser:
        conversations = Paginator(BotConversationState.objects.exclude(state='idle').select_related('user').order_by('-updated_at'), 20).get_page(request.GET.get('bot_page'))
    return render(request, 'panel/sessions.html', {
        'title': 'نشست‌ها', 'sessions': Paginator(sessions, 25).get_page(request.GET.get('page')),
        'current_session_key': request.session.session_key, 'conversations': conversations,
    })


@staff_member_required
@require_POST
def session_revoke(request, pk):
    sessions = PanelSession.objects.all()
    if not request.user.is_superuser:
        sessions = sessions.filter(user=request.user)
    item = get_object_or_404(sessions, pk=pk)
    is_current = item.session_id == request.session.session_key
    item.session.delete()
    if is_current:
        logout(request)
        return redirect('panel:login')
    messages.success(request, 'نشست بسته شد؛ ورود دوباره به رمز عبور نیاز دارد.')
    return redirect('panel:sessions')
