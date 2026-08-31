from django.urls import path

from . import views

app_name = 'panel'

urlpatterns = [
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
