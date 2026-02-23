from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib import messages

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
    my_events = Event.objects.filter(created_by=user)

    context = {
        'my_events': my_events,
        'button_label': button_label,
    }

    return render(request,
                  'accounts/faculty_dashboard.html',
                  context)


@login_required
def principal_dashboard(request):
    return render(request, 'accounts/principal_dashboard.html')

def home(request):
    return render(request, 'accounts/home.html')
    