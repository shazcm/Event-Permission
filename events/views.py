from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .forms import EventForm


@login_required
def create_event(request):

    if request.method == "POST":
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.created_by = request.user

            if request.user.sub_role == 'hod':
                event.department = request.user.department

            event.save()
            return redirect('faculty_dashboard')

    else:
        form = EventForm()

    return render(request, 'events/create_event.html', {'form': form})
