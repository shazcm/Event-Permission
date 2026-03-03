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

    path('principal/all/',
        views.view_all_events,
        name='view_all_events'),

    path('faculty/filter/',
        views.faculty_filter_events,
        name='faculty_filter_events'),

    path('change-venue/<int:event_id>/',
        views.change_event_venue,
        name='change_event_venue'),

     path('principal/approved/',
        views.principal_approved_events,
        name='principal_approved_events'),

    path('principal/rejected/',
        views.principal_rejected_events,
        name='principal_rejected_events'),

    path('check-conflict/',
        views.check_venue_conflict,
        name='check_venue_conflict'),

    path('events/<int:event_id>/',
        views.event_detail,
        name='event_detail'),

    path('events/<int:event_id>/download-report/',
        views.download_detailed_report,
        name='download_detailed_report'),

    path("search-events/", 
        views.search_events,
        name="search_events"),

]
