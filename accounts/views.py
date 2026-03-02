from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required

def login_view(request):
    if request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)

            # Role based redirect
            if user.is_superuser or user.is_staff and user.role == 'admin':
                return redirect('/admin/')

            elif user.role == 'principal':
                return redirect('principal_dashboard')

            elif user.role == 'faculty':
                return redirect('faculty_dashboard')
        else:
            messages.error(request, "Invalid username or password")

    return render(request, 'accounts/login.html')

from events.models import Event

@login_required
def faculty_dashboard(request):

    if request.user.role != 'faculty':
        return redirect('login')

    user = request.user

    # Dynamic button name
    if user.sub_role == 'hod':
        button_label = f"View All {user.department} Department Events"

    elif user.sub_role == 'nss':
        button_label = "View All NSS Events"

    elif user.sub_role == 'ncc':
        button_label = "View All NCC Events"

    elif user.sub_role == 'union':
        button_label = "View All Union Events"

    elif user.sub_role == 'other':
        button_label = "View All Other Events"

    else:
        button_label = "View All Events"

    # Only events created by this user
    my_events = Event.objects.filter(created_by=user).order_by('-created_at')

    context = {
        'my_events': my_events,
        'button_label': button_label,
        'my_event_count': my_events.count(),
        'pending_count': my_events.filter(status='pending').count(),
        'approved_count': my_events.filter(status='approved').count(),
        'completed_count': my_events.filter(status='completed').count(),
        'verified_count': my_events.filter(status='verified').count(),
        'rejected_count': my_events.filter(status='rejected').count(),
        'active_nav': 'faculty-dashboard',
    }

    return render(request,
                  'accounts/faculty_dashboard.html',
                  context)


@login_required
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

    context = {
        'total_events': total_events,
        'pending_count': pending_events.count(),
        'approved_count': approved_events.count(),
        'rejected_count': rejected_events.count(),
        'recent_pending': recent_pending,
        'calendar_events': calendar_events,
        'active_nav': 'principal-dashboard',
    }

    return render(request, 'accounts/principal_dashboard.html', context)


@login_required
def logout_view(request):
    logout(request)
    return redirect('login')
    
