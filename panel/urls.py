from django.urls import path

from . import views
from . import control_views, security_views
from .auth import PanelLoginView, PanelLogoutView

app_name = 'panel'

urlpatterns = [
    path('login/', PanelLoginView.as_view(), name='login'),
    path('logout/', PanelLogoutView.as_view(), name='logout'),
    path('password-reset/', security_views.password_reset_request, name='password_reset'),
    path('password-reset/code/', security_views.password_reset_verify, name='password_reset_verify'),
    path('password-reset/new/', security_views.password_reset_confirm, name='password_reset_confirm'),
    path('sessions/', security_views.sessions_list, name='sessions'),
    path('account/recovery-email/', security_views.recovery_email, name='recovery_email'),
    path('sessions/<int:pk>/revoke/', security_views.session_revoke, name='session_revoke'),
    path('bot/', control_views.bot_control, name='bot_control'),
    path('bot/toggle/', control_views.bot_toggle, name='bot_toggle'),
    path('bot/maintain/', control_views.bot_maintain, name='bot_maintain'),
    path('bot/status/', control_views.maintenance_status, name='maintenance_status'),
    path('', views.dashboard, name='dashboard'),
    path('today/', views.today_appointments, name='today_appointments'),
    path('appointments/', views.appointments_list, name='appointments'),
    path('appointments/new/', views.appointment_create, name='appointment_create'),
    path('appointments/<int:pk>/edit/', views.appointment_edit, name='appointment_edit'),
    path('appointments/<int:pk>/cancel/', views.appointment_cancel, name='appointment_cancel'),
    path('barbers/', views.barbers_list, name='barbers'),
    path('barbers/new/', views.barber_create, name='barber_create'),
    path('barbers/<int:pk>/edit/', views.barber_edit, name='barber_edit'),
    path('barbers/<int:pk>/toggle/', views.barber_toggle, name='barber_toggle'),
    path('barbers/<int:pk>/portfolio/', views.barber_portfolio, name='barber_portfolio'),
    path('barbers/<int:pk>/portfolio/<int:work_pk>/edit/', views.portfolio_edit, name='portfolio_edit'),
    path('barbers/<int:pk>/portfolio/<int:work_pk>/delete/', views.portfolio_delete, name='portfolio_delete'),
    path('schedules/', views.schedules_list, name='schedules'),
    path('schedules/new/', views.schedule_create, name='schedule_create'),
    path('schedules/<int:pk>/edit/', views.schedule_edit, name='schedule_edit'),
    path('schedules/<int:pk>/delete/', views.schedule_delete, name='schedule_delete'),
    path('blocked-times/', views.blocked_times_list, name='blocked_times'),
    path('blocked-times/new/', views.blocked_time_create, name='blocked_time_create'),
    path('blocked-times/<int:pk>/edit/', views.blocked_time_edit, name='blocked_time_edit'),
    path('blocked-times/<int:pk>/delete/', views.blocked_time_delete, name='blocked_time_delete'),
    path('users/', views.users_list, name='users'),
    path('settings/', views.salon_settings, name='salon_settings'),
]
