from django.urls import path
from . import views

urlpatterns = [
    path('create/', views.create_event, name='create_event'),

    path('principal/pending/',
         views.principal_pending_events,
         name='principal_pending_events'),

    path('principal/action/<int:event_id>/<str:action>/',
         views.principal_event_action,
         name='principal_event_action'),

    path('post-upload/<int:event_id>/',
        views.post_event_upload,
        name='post_event_upload'),

    path('principal/verify/',
        views.principal_verify_list,
        name='principal_verify_list'),

    path('principal/verify/<int:event_id>/',
        views.principal_verify_event,
        name='principal_verify_event'),
    
    path('principal/analytics/',
        views.analytics_dashboard,
        name='analytics_dashboard'),

    path('principal/filter/',
        views.filter_events,
        name='filter_events'),


]
