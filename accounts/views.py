from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib import messages
from events.models import Event
from django.db.models import Count
from django.utils import timezone
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

from django.contrib.auth.decorators import login_required

@login_required
def faculty_dashboard(request):
    return render(request, 'accounts/faculty_dashboard.html')


@login_required
def principal_dashboard(request):

    if request.user.role != 'principal':
        return redirect('login')

    total_events = Event.objects.count()
    pending_count = Event.objects.filter(status='pending').count()
    verified_count = Event.objects.filter(status='verified').count()
    completed_count = Event.objects.filter(status='completed').count()

    # Recent 5 events
    recent_events = Event.objects.order_by('-created_at')[:5]

    context = {
        'total_events': total_events,
        'pending_count': pending_count,
        'verified_count': verified_count,
        'completed_count': completed_count,
        'recent_events': recent_events,
    }

    return render(request, 'accounts/principal_dashboard.html', context)

def home(request):
    return render(request, 'accounts/home.html')
    