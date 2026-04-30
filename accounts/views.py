from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from .models import Notification
from django.shortcuts import get_object_or_404
from django.utils import timezone


def _redirect_for_role(user):
    if user.is_superuser or (user.is_staff and user.role == 'admin'):
        return redirect('/admin/')

    if user.role == 'principal':
        return redirect('principal_dashboard')

    if user.role == 'faculty':
        return redirect('faculty_dashboard')

    return redirect('logout')


@never_cache
def login_view(request):
    if request.user.is_authenticated:
        return _redirect_for_role(request.user)

    if request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return _redirect_for_role(user)
        else:
            messages.error(request, "Invalid username or password")

    return render(request, 'accounts/login.html')

from events.models import Event


@never_cache
@login_required(login_url='/login/')
def faculty_dashboard(request):

    if request.user.role != 'faculty':
        return redirect('login')

    user = request.user

    # Only events created by this user
    my_events = Event.objects.filter(created_by=user).order_by('-created_at')
    unread_notifications = request.user.notifications.filter(is_read=False)
    unread_count = unread_notifications.count()
    recent_notifications = request.user.notifications.order_by('-created_at')[:5]
    today = timezone.now().date()

    # Upcoming: approved events whose start_date hasn't passed yet
    upcoming_events = my_events.filter(status='approved', start_date__gte=today).order_by('start_date')
    rejected_events = my_events.filter(status='rejected').order_by('-created_at')

    # Recent activity: last 6 notifications for this user
    recent_activity = request.user.notifications.select_related('event').order_by('-created_at')[:6]

    context = {
        'my_events': my_events,
        'my_event_count': my_events.count(),
        'pending_count': my_events.filter(status='pending').count(),
        'approved_count': my_events.filter(status='approved').count(),
        'completed_count': my_events.filter(status='completed').count(),
        'verified_count': my_events.filter(status='verified').count(),
        'rejected_count': my_events.filter(status='rejected').count(),
        'upcoming_count': upcoming_events.count(),
        'upcoming_events': upcoming_events,
        'rejected_events': rejected_events,
        'recent_activity': recent_activity,
        'today': today,
        'active_nav': 'faculty-dashboard',
        'unread_count': unread_count,
        'recent_notifications': recent_notifications,
    }

    return render(request,
                  'accounts/faculty_dashboard.html',
                  context)

@never_cache
@login_required(login_url='/login/')
def principal_dashboard(request):

    if request.user.role != 'principal':
        return redirect('login')

    total_events = Event.objects.count()
    pending_events = Event.objects.filter(status='pending')
    approved_events = Event.objects.filter(status='approved')
    rejected_events = Event.objects.filter(status='rejected')

    recent_pending = pending_events.order_by('-created_at')[:3]

    calendar_events = []
    for event in Event.objects.select_related('department').order_by('start_date'):
        calendar_events.append({
            'title': event.title,
            'status': event.status,
            'start': event.start_date.isoformat(),
            'end': event.end_date.isoformat(),
            'department': event.department.name if event.department else 'General',
        })
    unread_notifications = request.user.notifications.filter(is_read=False)
    unread_count = unread_notifications.count()
    recent_notifications = request.user.notifications.order_by('-created_at')[:5]
    context = {
        'total_events': total_events,
        'pending_count': pending_events.count(),
        'approved_count': approved_events.count(),
        'rejected_count': rejected_events.count(),
        'recent_pending': recent_pending,
        'calendar_events': calendar_events,

        # 🔔 ADD THESE
        'unread_count': unread_count,
        'recent_notifications': recent_notifications,

        'active_nav': 'principal-dashboard',
}
    return render(request, 'accounts/principal_dashboard.html', context)

@never_cache
@login_required(login_url='/login/')
def logout_view(request):
    logout(request)
    request.session.flush()
    return redirect('login')
@login_required(login_url='/login/')
def notification_redirect(request, pk):
    notification = get_object_or_404(
        Notification,
        id=pk,
        recipient=request.user
    )

    notification.is_read = True
    notification.save()
    # 🔴 PRINCIPAL LOGIC
    if request.user.role == 'principal':

        if notification.type == 'submitted':
            return redirect('principal_pending_events')

        if notification.type == 'completed':
            return redirect('principal_verify_list')

        return redirect('principal_dashboard')

    # 🟢 FACULTY LOGIC
    if request.user.role == 'faculty':

        if notification.event:
            return redirect('event_detail', event_id=notification.event.id)

        return redirect('faculty_dashboard')

    return redirect('home')