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
def create_event(request):

    if request.method == "POST":
        form = EventForm(request.POST, user=request.user)

        if form.is_valid():
            event = form.save(commit=False)

            event.created_by = request.user

            if request.user.sub_role == 'hod':
                event.department = request.user.department

            event.save()

            messages.success(request, "Event submitted successfully.")

            # Reload empty form after submission
            form = EventForm(user=request.user)

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

    event = get_object_or_404(Event, id=event_id)

    if action == 'approve':

        # 🔴 Check for overlapping approved events (exclude itself)
        conflict_exists = Event.objects.filter(
            venue=event.venue,
            status='approved',
            start_date__lte=event.end_date,
            end_date__gte=event.start_date
        ).exclude(id=event.id).exists()

        if conflict_exists:
            messages.error(
                request,
                "Approval blocked! Another approved event overlaps at this venue during the selected date range."
            )
            return redirect('principal_pending_events')

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
def view_all_events(request):

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

    # 📅 Date range filter (UPDATED)
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    if start_date and end_date:
        events = events.filter(
            start_date__lte=end_date,
            end_date__gte=start_date
        )
    elif start_date:
        events = events.filter(end_date__gte=start_date)
    elif end_date:
        events = events.filter(start_date__lte=end_date)

    departments = Department.objects.all()

    context = {
        'events': events,
        'departments': departments,
    }

    return render(request, 
                  'events/view_all_events.html', 
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

    # 📅 Date range filter (UPDATED)
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    if start_date and end_date:
        events = events.filter(
            start_date__lte=end_date,
            end_date__gte=start_date
        )
    elif start_date:
        events = events.filter(end_date__gte=start_date)
    elif end_date:
        events = events.filter(start_date__lte=end_date)

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

    today = timezone.now().date()

    approved_events = Event.objects.filter(
        status='approved'
    ).order_by('-start_date')

    context = {
        'approved_events': approved_events,
        'today': today
    }

    return render(
        request,
        'events/principal_approved.html',
        context
    )


from django.db.models import Q
from django.utils import timezone

@login_required
def change_event_venue(request, event_id):

    if request.user.role != 'principal':
        return redirect('login')

    event = get_object_or_404(Event, id=event_id)

    # Only approved events can change venue
    if event.status != 'approved':
        messages.error(request, "Venue can only be changed for approved events.")
        return redirect('principal_approved_events')

    # Prevent change if event already started
    today = timezone.now().date()
    if event.start_date < today:
        messages.error(request, "Cannot change venue. Event has already started or passed.")
        return redirect('principal_approved_events')

    class VenueUpdateForm(forms.ModelForm):
        class Meta:
            model = Event
            fields = ['venue']

    if request.method == 'POST':
        form = VenueUpdateForm(request.POST, instance=event)

        if form.is_valid():
            selected_venue = form.cleaned_data['venue']

            # 🔥 CORRECT OVERLAP DETECTION
            conflict_exists = Event.objects.filter(
                venue=selected_venue,
                status='approved'
            ).exclude(id=event.id).filter(
                start_date__lte=event.end_date,
                end_date__gte=event.start_date
            ).exists()

            if conflict_exists:
                messages.error(
                    request,
                    "Conflict! Another approved event overlaps at this venue during the selected date range."
                )
                return render(request,
                              'events/change_venue.html',
                              {'form': form, 'event': event})

            form.save()
            messages.success(request, "Venue updated successfully.")
            return redirect('principal_approved_events')

    else:
        form = VenueUpdateForm(instance=event)

    return render(request,
                  'events/change_venue.html',
                  {'form': form, 'event': event})

from django.http import JsonResponse
from datetime import datetime

@login_required
def check_venue_conflict(request):

    venue_id = request.GET.get('venue')
    new_start = request.GET.get('start_date')
    new_end = request.GET.get('end_date')

    if venue_id and new_start and new_end:

        new_start = datetime.strptime(new_start, "%Y-%m-%d").date()
        new_end = datetime.strptime(new_end, "%Y-%m-%d").date()

        approved_event = Event.objects.filter(
            venue_id=venue_id,
            status='approved',
            start_date__lte=new_end,
            end_date__gte=new_start
        ).first()

        if approved_event:
            return JsonResponse({
                'status': 'approved',
                'title': approved_event.title
            })

        pending_event = Event.objects.filter(
            venue_id=venue_id,
            status='pending',
            start_date__lte=new_end,
            end_date__gte=new_start
        ).first()

        if pending_event:
            return JsonResponse({
                'status': 'pending',
                'title': pending_event.title
            })

    return JsonResponse({'status': 'clear'})