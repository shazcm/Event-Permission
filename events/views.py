from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .forms import EventForm
from .models import Event, Department
from django.utils import timezone
from .forms import PostEventForm
from django.db.models import Count
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django import forms
from .models import Venue
from django.contrib import messages

@login_required
def change_event_venue(request, event_id):

    if request.user.role != 'principal':
        return redirect('login')

    event = get_object_or_404(Event, id=event_id)

    # ✅ Only approved events
    if event.status != 'approved':
        messages.error(request, "Venue can only be changed for approved events.")
        return redirect('filter_events')

    # ✅ Prevent change after event date passed
    today = timezone.now().date()

    if event.event_date < today:
        messages.error(request, "Cannot change venue. Event date has already passed.")
        return redirect('filter_events')

    class VenueUpdateForm(forms.ModelForm):
        class Meta:
            model = Event
            fields = ['venue']

    if request.method == 'POST':
        form = VenueUpdateForm(request.POST, instance=event)
        if form.is_valid():
            form.save()
            messages.success(request, "Venue updated successfully.")
            return redirect('filter_events')
    else:
        form = VenueUpdateForm(instance=event)

    return render(request,
                  'events/change_venue.html',
                  {'form': form, 'event': event})


@login_required
def create_event(request):

    if request.method == "POST":
        form = EventForm(request.POST, user=request.user)
        if form.is_valid():
            event = form.save(commit=False)
            event.created_by = request.user

            if request.user.sub_role == 'hod':
                event.department = request.user.department

            event.save()
            return redirect('faculty_dashboard')

    else:
        form = EventForm(user=request.user)

    return render(request, 'events/create_event.html', {'form': form})

@login_required
def principal_pending_events(request):

    if request.user.role != 'principal':
        return redirect('login')

    events = Event.objects.filter(status='pending').order_by('-created_at')

    return render(
        request,
        'events/principal_pending.html',
        {'events': events}
    )

@login_required
def principal_event_action(request, event_id, action):

    if request.user.role != 'principal':
        return redirect('login')

    event = Event.objects.get(id=event_id)

    if action == 'approve':
        event.status = 'approved'
        event.principal_remark = ''

    elif action == 'reject':
        remark = request.POST.get('remark')
        event.status = 'rejected'
        event.principal_remark = remark

    event.save()

    return redirect('principal_pending_events')


@login_required
def post_event_upload(request, event_id):

    event = Event.objects.get(id=event_id)

    if event.created_by != request.user:
        return redirect('faculty_dashboard')

    if request.method == "POST":
        form = PostEventForm(request.POST, request.FILES, instance=event)
        if form.is_valid():
            ev = form.save(commit=False)
            ev.status = 'completed'
            ev.completed_at = timezone.now()
            ev.save()
            return redirect('faculty_dashboard')

    else:
        form = PostEventForm(instance=event)

    return render(request,
                  'events/post_upload.html',
                  {'form': form, 'event': event})

@login_required
def principal_verify_list(request):

    if request.user.role != 'principal':
        return redirect('login')

    events = Event.objects.filter(status='completed')

    return render(request,
                  'events/principal_verify.html',
                  {'events': events})

@login_required
def principal_verify_event(request, event_id):

    if request.user.role != 'principal':
        return redirect('login')

    event = Event.objects.get(id=event_id)
    event.status = 'verified'
    event.save()

    return redirect('principal_verify_list')


@login_required
def analytics_dashboard(request):

    if request.user.role != 'principal':
        return redirect('login')

    total_events = Event.objects.count()
    pending = Event.objects.filter(status='pending').count()
    approved = Event.objects.filter(status='approved').count()
    completed = Event.objects.filter(status='completed').count()
    verified = Event.objects.filter(status='verified').count()

    context = {
        'total': total_events,
        'pending': pending,
        'approved': approved,
        'completed': completed,
        'verified': verified,
    }

    return render(request, 'events/analytics.html', context)


@login_required
def filter_events(request):

    if request.user.role != 'principal':
        return redirect('login')

    events = Event.objects.all()

    # 🔎 Search by title
    search = request.GET.get('search')
    if search:
        events = events.filter(title__icontains=search)

    # 📌 Status filter
    status = request.GET.get('status')
    if status:
        events = events.filter(status=status)

    # 🏢 Department filter
    department = request.GET.get('department')
    if department:
        events = events.filter(department_id=department)

    # 📂 Category filter
    category = request.GET.get('category')
    if category:
        events = events.filter(category=category)

    # 👦👧 Participation filter
    participation = request.GET.get('participation')
    if participation:
        events = events.filter(participation_type=participation)

    # 📅 Date range filter
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    if start_date:
        events = events.filter(event_date__gte=start_date)

    if end_date:
        events = events.filter(event_date__lte=end_date)

    departments = Department.objects.all()

    context = {
        'events': events,
        'departments': departments,
    }

    return render(request,
                  'events/filter_events.html',
                  context)



@login_required
def faculty_filter_events(request):

    if request.user.role != 'faculty':
        return redirect('login')

    user = request.user

    # Base queryset
    if user.sub_role == 'hod':
        events = Event.objects.filter(department=user.department)
        page_title = f"{user.department} Department Events"

    elif user.sub_role == 'nss':
        events = Event.objects.filter(category='nss')
        page_title = "NSS Events"

    elif user.sub_role == 'ncc':
        events = Event.objects.filter(category='ncc')
        page_title = "NCC Events"

    elif user.sub_role == 'union':
        events = Event.objects.filter(category='union')
        page_title = "Union Events"

    elif user.sub_role == 'other':
        events = Event.objects.filter(category='other')
        page_title = "Other Events"

    else:
        events = Event.objects.none()
        page_title = "Events"

    # 🔎 Search
    search = request.GET.get('search')
    if search:
        events = events.filter(title__icontains=search)

    # 📌 Status filter
    status = request.GET.get('status')
    if status:
        events = events.filter(status=status)

    # 👥 Participation filter
    participation = request.GET.get('participation')
    if participation:
        events = events.filter(participation_type=participation)

    # 📅 Date range filter
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    if start_date:
        events = events.filter(event_date__gte=start_date)

    if end_date:
        events = events.filter(event_date__lte=end_date)

    context = {
        'events': events,
        'page_title': page_title,
    }

    return render(request,
                  'events/faculty_filter.html',
                  context)



@login_required
def principal_approved_events(request):

    if request.user.role != 'principal':
        return redirect('login')

    approved_events = Event.objects.filter(status='approved').order_by('-event_date')

    return render(request,
                  'events/principal_approved.html',
                  {'approved_events': approved_events})


@login_required
def change_event_venue(request, event_id):

    if request.user.role != 'principal':
        return redirect('login')

    event = get_object_or_404(Event, id=event_id)

    # ✅ Only approved events
    if event.status != 'approved':
        messages.error(request, "Venue can only be changed for approved events.")
        return redirect('filter_events')

    # ✅ Prevent change after event date passed
    today = timezone.now().date()

    if event.event_date < today:
        messages.error(request, "Cannot change venue. Event date has already passed.")
        return redirect('filter_events')

    class VenueUpdateForm(forms.ModelForm):
        class Meta:
            model = Event
            fields = ['venue']

    if request.method == 'POST':
        form = VenueUpdateForm(request.POST, instance=event)
        if form.is_valid():
            form.save()
            messages.success(request, "Venue updated successfully.")
            return redirect('filter_events')
    else:
        form = VenueUpdateForm(instance=event)

    return render(request,
                  'events/change_venue.html',
                  {'form': form, 'event': event})