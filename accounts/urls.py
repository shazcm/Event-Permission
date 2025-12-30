from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('faculty/dashboard/', views.faculty_dashboard, name='faculty_dashboard'),
    path('principal/dashboard/', views.principal_dashboard, name='principal_dashboard'),
]