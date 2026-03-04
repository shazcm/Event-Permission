from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='home'),
    path('login/', views.login_view, name='login'),
    # Backward-compatible alias in case any redirect still points here.
    path('accounts/login/', views.login_view, name='accounts_login'),
    path('logout/', views.logout_view, name='logout'),
    path('faculty/dashboard/', views.faculty_dashboard, name='faculty_dashboard'),
    path('principal/dashboard/', views.principal_dashboard, name='principal_dashboard'),
    path('notification/<int:pk>/',
     views.notification_redirect,
     name='notification_redirect'),
]
