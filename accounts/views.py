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
            if user.role == 'faculty':
                return redirect('faculty_dashboard')
            elif user.role == 'principal':
                return redirect('principal_dashboard')
            elif user.role == 'admin':
                return redirect('/admin')
        else:
            messages.error(request, "Invalid username or password")

    return render(request, 'accounts/login.html')

from django.contrib.auth.decorators import login_required

@login_required
def faculty_dashboard(request):
    return render(request, 'accounts/faculty_dashboard.html')


@login_required
def principal_dashboard(request):
    return render(request, 'accounts/principal_dashboard.html')

def home(request):
    return render(request, 'accounts/home.html')
    