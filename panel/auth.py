from functools import partial
from urllib.parse import urlsplit

from django.contrib.admin.views.decorators import staff_member_required as django_staff_required
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect
from django.urls import reverse

from .forms import PanelAuthenticationForm


staff_member_required = partial(django_staff_required, login_url='panel:login')


class PanelLoginView(LoginView):
    template_name = 'panel/login.html'
    authentication_form = PanelAuthenticationForm
    extra_context = {'title': 'ورود به پنل مدیریت'}
    next_page = 'panel:dashboard'

    def get_success_url(self):
        target = super().get_success_url()
        path = urlsplit(target).path
        if not path.startswith(reverse('panel:dashboard')) or path in {
            reverse('panel:login'), reverse('panel:logout'),
        }:
            return reverse('panel:dashboard')
        return target

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_active and request.user.is_staff:
            return redirect(self.get_success_url())
        return super().get(request, *args, **kwargs)


class PanelLogoutView(LogoutView):
    next_page = 'panel:login'
