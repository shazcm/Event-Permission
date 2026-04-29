from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .forms import EventForm
from .models import Event, Department, Hashtag
from django.utils import timezone
from .forms import PostEventForm
from django.db.models import Count
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django import forms
from .models import Venue
from django.contrib import messages
from django.http import JsonResponse
from datetime import datetime
from django.utils import timezone
from .models import EventPhoto
from .forms import EventPhotoForm
from .hashtags import parse_hashtags
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from django.http import HttpResponse
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.platypus import ListFlowable, ListItem
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER
import os
import re
from django.views.decorators.cache import never_cache
from accounts.utils import notify
from accounts.models import User


def _is_ajax_request(request):
    return (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or request.GET.get("ajax") == "1"
    )


def _apply_event_search(queryset, query):
    if not query:
        return queryset

    return queryset.filter(
        Q(title__icontains=query) |
        Q(description__icontains=query) |
        Q(category__icontains=query) |
        Q(participation_type__icontains=query) |
        Q(status__icontains=query) |
        Q(department__name__icontains=query) |
        Q(venue__name__icontains=query) |
        Q(hashtags__name__icontains=query) |
        Q(created_by__username__icontains=query) |
        Q(created_by__first_name__icontains=query) |
        Q(created_by__last_name__icontains=query)
    ).distinct()


def _parse_search_and_hashtags(search_query, legacy_hashtag):
    search_text = (search_query or "").strip()
    legacy_text = (legacy_hashtag or "").strip()

    hashtag_tokens = []
    text_tokens = []

    if search_text:
        for token in re.split(r"[\s,]+", search_text):
            if not token:
                continue
            if token.startswith("#"):
                cleaned = token.lstrip("#").lower()
                if cleaned:
                    hashtag_tokens.append(cleaned)
            else:
                text_tokens.append(token)

    if legacy_text:
        for token in re.split(r"[\s,]+", legacy_text):
            if not token:
                continue
            cleaned = token.lstrip("#").lower()
            if cleaned:
                hashtag_tokens.append(cleaned)

    deduped_hashtags = list(dict.fromkeys(hashtag_tokens))
    deduped_text = " ".join(text_tokens)
    return deduped_text, deduped_hashtags


def _parse_csv_values(raw_value):
    if not raw_value:
        return []
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def _normalize_filter_value(raw_value):
    if raw_value is None:
        return ""
    cleaned = str(raw_value).strip()
    if cleaned.lower() in {"none", "null"}:
        return ""
    return cleaned


def _remove_query_param(query_string, key, value=None):
    params = query_string.copy()
    values = params.getlist(key)
    if value is None or len(values) <= 1:
        params.pop(key, None)
        return params.urlencode()

    params.setlist(key, [v for v in values if v != value])
    if not params.getlist(key):
        params.pop(key, None)
    return params.urlencode()


def _apply_quick_filter(events, quick_filter):
    today = timezone.localdate()
    if quick_filter == "completed":
        return events.filter(status="completed")
    if quick_filter == "verified":
        return events.filter(status="verified")
    if quick_filter == "upcoming":
        return events.filter(start_date__gte=today)
    return events



@login_required(login_url='/login/')
def create_event(request):

    if request.method == "POST":
        form = EventForm(request.POST, user=request.user)

        if form.is_valid():
            event = form.save(commit=False)
            user=request.user
            if user.sub_role == 'hod':
                event.category = 'department'
            elif user.sub_role == 'nss':
                event.category = 'nss'
            elif user.sub_role == 'ncc':
                event.category = 'ncc'
            elif user.sub_role == 'union':
                event.category = 'union'
            else:
                event.category = 'other'

            event.created_by = request.user

            if request.user.sub_role == 'hod':
                event.department = request.user.department

            event.save()

            principal = User.objects.filter(role='principal').first()

            if principal:
                notify(
                    recipient=principal,
                    sender=request.user,
                    event=event,
                    type='submitted',
                    message=f"New event '{event.title}' submitted for approval."
                )

            messages.success(request, "Event submitted successfully.")

            # Reload empty form after submission
            form = EventForm(user=request.user)

    else:
        form = EventForm(user=request.user)

    return render(
        request,
        'events/create_event.html',
        {
            'form': form,
            'active_nav': 'faculty-create',
        }
    )

@login_required(login_url='/login/')
def principal_pending_events(request):

    if request.user.role != 'principal':
        return redirect('login')

    events = Event.objects.filter(status='pending').order_by('-created_at')

    return render(
        request,
        'events/principal_pending.html',
        {
            'events': events,
            'active_nav': 'principal-pending',
        }
    )

@login_required(login_url='/login/')
def principal_event_action(request, event_id, action):

    if request.user.role != 'principal':
        return redirect('login')

    event = get_object_or_404(Event, id=event_id)

    if action == 'approve':
        if event.status != 'pending':
            messages.error(request, "Only pending events can be approved.")
            return redirect('principal_pending_events')

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
        if event.status not in {'pending', 'approved'}:
            messages.error(request, "Only pending or approved events can be rejected.")
            return redirect('principal_pending_events')
        remark = request.POST.get('remark')
        if not remark:
            messages.error(request, "Reason for rejection is required.")
            return redirect('principal_pending_events')
        event.status = 'rejected'
        event.principal_remark = remark

    event.save()
    

    if action == 'approve':
        notify(
            recipient=event.created_by,
            sender=request.user,
            event=event,
            type='approved',
            message=f"Your event '{event.title}' has been approved."
        )

    elif action == 'reject':
        notify(
            recipient=event.created_by,
            sender=request.user,
            event=event,
            type='rejected',
            message=f"Your event '{event.title}' has been rejected."
        )

    return redirect('principal_pending_events')


@login_required(login_url='/login/')
def faculty_request_cancel_event(request, event_id):
    if request.method != "POST":
        return redirect('faculty_filter_events')

    if request.user.role != 'faculty':
        return redirect('login')

    event = get_object_or_404(Event, id=event_id)

    if event.created_by != request.user:
        messages.error(request, "You can only request cancellation for your own events.")
        return redirect('event_detail', event_id=event.id)

    if event.status not in {'pending', 'approved'}:
        messages.error(request, "Cancellation is allowed only for pending or approved events.")
        return redirect('event_detail', event_id=event.id)

    event.status = 'cancelled'
    event.is_cancellation_requested = False
    event.cancellation_reason = ""
    event.cancellation_review_remark = ""
    event.cancellation_requested_at = None
    event.save()

    principal = User.objects.filter(role='principal').first()
    if principal:
        notify(
            recipient=principal,
            sender=request.user,
            event=event,
            type='cancel_requested',
            message=f"Event '{event.title}' was cancelled by faculty."
        )

    messages.success(request, "Event cancelled successfully.")
    return redirect('event_detail', event_id=event.id)


@login_required(login_url='/login/')
def principal_cancel_event_action(request, event_id, action):
    messages.error(request, "Cancellation approval flow is disabled.")
    return redirect('principal_pending_events')


@login_required(login_url='/login/')
def principal_reject_approved_event(request, event_id):
    if request.method != "POST":
        return redirect('principal_approved_events')

    if request.user.role != 'principal':
        return redirect('login')

    event = get_object_or_404(Event, id=event_id)
    if event.status != 'approved':
        messages.error(request, "Only approved events can be rejected from this screen.")
        return redirect('principal_approved_events')

    remark = (request.POST.get('remark') or "").strip()
    if not remark:
        messages.error(request, "Reason for rejection is required.")
        return redirect('principal_approved_events')

    event.status = 'rejected'
    event.principal_remark = remark
    event.save()
    notify(
        recipient=event.created_by,
        sender=request.user,
        event=event,
        type='rejected',
        message=f"Your approved event '{event.title}' has been rejected."
    )
    messages.success(request, "Approved event rejected successfully.")
    return redirect('principal_approved_events')


  # adjust import if needed


def generate_auto_report(event):

    # Organizer Text
    if event.created_by.sub_role == "hod":
        organizer_text = f"The Department of {event.department}"
    elif event.created_by.sub_role == "nss":
        organizer_text = "The NSS Unit"
    elif event.created_by.sub_role == "ncc":
        organizer_text = "The NCC Unit"
    elif event.created_by.sub_role == "union":
        organizer_text = "The College Union"
    else:
        organizer_text = "The organizing committee"

    # Date Formatting
    if event.start_date == event.end_date:
        date_text = event.start_date.strftime("%d %B %Y")
    else:
        date_text = (
            f"{event.start_date.strftime('%d %B %Y')} "
            f"to {event.end_date.strftime('%d %B %Y')}"
        )

    # Chief Guest Text
    chief_guest_text = ""
    if event.chief_guest:
        chief_guest_text = (
            f" The programme was graced by "
            f"{event.chief_guest} as the Chief Guest."
        )

    # Attendance & Photos
    photo_count = event.photos.count()
    attendance_status = (
        "The attendance record has been officially submitted."
        if event.attendance_file
        else "No attendance record was submitted."
    )

    # Final Report
    return f"""
{organizer_text} successfully organized the event titled "{event.title}" 
at {event.venue} on {date_text}.{chief_guest_text}

The event witnessed active participation and was conducted 
in a well-structured manner.

{attendance_status}

A total of {photo_count} photographic records were documented 
as part of the official event proceedings.
"""

@login_required(login_url='/login/')
def post_event_upload(request, event_id):

    event = get_object_or_404(Event, id=event_id)

    # Only event creator can access
    if event.created_by != request.user:
        return redirect('faculty_dashboard')

    if request.method == "POST":
        raw_hashtags = request.POST.get("hashtags", "")
        try:
            parsed_tags = parse_hashtags(raw_hashtags)
        except ValueError as exc:
            messages.error(request, str(exc))
            return render(request, 'events/post_upload.html', {
                'event': event,
                'active_nav': 'faculty-dashboard',
                'hashtag_input': raw_hashtags,
            })

        # ---- Handle Attendance Upload ----
        if request.FILES.get('attendance_file'):
            event.attendance_file = request.FILES.get('attendance_file')

        # ---- Handle Image Upload (Max 5) ----
        images = request.FILES.getlist('images')

        existing_count = event.photos.count()
        new_count = len(images)

        if existing_count + new_count > 5:
            messages.error(request, "An event can have maximum 5 photos.")
        else:
            for image in images:
                EventPhoto.objects.create(
                    event=event,
                    image=image
                )

        # ---- Generate Report Button ----
        if "generate_report" in request.POST:
            event.report_text = generate_auto_report(event)
            event.save()

        # ---- Submit Final Report Button ----
        if "submit_report" in request.POST:
            event.report_text = request.POST.get("report_text")
            event.status = "completed"
            event.save()
            hashtag_objects = [
                Hashtag.objects.get_or_create(name=tag)[0]
                for tag in parsed_tags
            ]
            event.hashtags.set(hashtag_objects)
            return redirect('faculty_dashboard')

        event.save()
        hashtag_objects = [
            Hashtag.objects.get_or_create(name=tag)[0]
            for tag in parsed_tags
        ]
        event.hashtags.set(hashtag_objects)
        principal = User.objects.filter(role='principal').first()

        if principal:
            notify(
                recipient=principal,
                sender=request.user,
                event=event,
                type='completed',
                message=f"Event '{event.title}' marked as completed. Please verify."
            )

    return render(request, 'events/post_upload.html', {
        'event': event,
        'active_nav': 'faculty-dashboard',
        'hashtag_input': " ".join(f"#{tag.name}" for tag in event.hashtags.order_by('name')),
    })

@login_required(login_url='/login/')
def principal_verify_list(request):

    if request.user.role != 'principal':
        return redirect('login')

    events = Event.objects.filter(status='completed')

    return render(request,
                  'events/principal_verify.html',
                  {
                      'events': events,
                      'active_nav': 'principal-verify',
                  })

@login_required(login_url='/login/')
def principal_verify_event(request, event_id):

    if request.user.role != 'principal':
        return redirect('login')

    event = get_object_or_404(Event, id=event_id)

    if request.method == "POST" and event.status == "completed":
        event.status = 'verified'
        event.save()

    return redirect('event_detail', event_id=event.id)


@login_required(login_url='/login/')
def analytics_dashboard(request):

    if request.user.role != 'principal':
        return redirect('login')

    total_events = Event.objects.count()
    pending = Event.objects.filter(status='pending').count()
    approved = Event.objects.filter(status='approved').count()
    completed = Event.objects.filter(status='completed').count()
    verified = Event.objects.filter(status='verified').count()
    rejected = Event.objects.filter(status='rejected').count()

    status_labels = ['Pending', 'Approved', 'Completed', 'Verified', 'Rejected']
    status_counts = [pending, approved, completed, verified, rejected]

    category_labels = ['Department', 'NSS', 'NCC', 'Union', 'Other']
    category_keys = ['department', 'nss', 'ncc', 'union', 'other']
    category_counts = [
        Event.objects.filter(category=category_key).count()
        for category_key in category_keys
    ]

    context = {
        'total': total_events,
        'pending': pending,
        'approved': approved,
        'completed': completed,
        'verified': verified,
        'rejected': rejected,
        'status_labels': status_labels,
        'status_counts': status_counts,
        'category_labels': category_labels,
        'category_counts': category_counts,
        'active_nav': 'principal-analytics',
    }

    return render(request, 'events/analytics.html', context)


@login_required(login_url='/login/')
def view_all_events(request):

    if request.user.role != 'principal':
        return redirect('login')

    events = Event.objects.all().select_related(
        'created_by', 'department', 'venue'
    ).order_by('-start_date')

    search = request.GET.get('search', '')
    legacy_hashtag = request.GET.get('hashtag', '')
    text_query, hashtag_filters = _parse_search_and_hashtags(search, legacy_hashtag)
    events = _apply_event_search(events, text_query)
    if hashtag_filters:
        events = events.filter(hashtags__name__in=hashtag_filters).distinct()

    quick = request.GET.get('quick', 'all')
    if quick not in {'all', 'completed', 'verified', 'upcoming'}:
        quick = 'all'
    events = _apply_quick_filter(events, quick)

    # 🏢 Department filter
    department = _normalize_filter_value(request.GET.get('department'))
    if department:
        events = events.filter(department_id=department)

    # 📂 Category filter
    category = _normalize_filter_value(request.GET.get('category'))
    category_values = _parse_csv_values(category)
    if category_values:
        events = events.filter(category__in=category_values)

    # 👦👧 Participation filter
    participation = _normalize_filter_value(request.GET.get('participation'))
    if participation:
        events = events.filter(participation_type=participation)

    # 📅 Date range filter (UPDATED)
    start_date = _normalize_filter_value(request.GET.get('start_date'))
    end_date = _normalize_filter_value(request.GET.get('end_date'))

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
        'quick': quick,
        'selected_categories': category_values,
        'selected_participation': participation,
        'selected_department': department,
        'search_value': _normalize_filter_value(search),
        'start_date_value': start_date,
        'end_date_value': end_date,
        'active_filter_tags': [],
        'current_query': request.GET.copy(),
        'active_nav': 'principal-all',
    }

    active_tags = []
    current_query = request.GET.copy()
    if search.strip():
        active_tags.append({
            'label': f"Search: {search.strip()}",
            'remove_query': _remove_query_param(current_query, 'search'),
        })
    if quick != 'all':
        active_tags.append({
            'label': f"Quick: {quick.title()}",
            'remove_query': _remove_query_param(current_query, 'quick'),
        })
    for cat in category_values:
        active_tags.append({
            'label': f"Category: {cat.title()}",
            'remove_query': _remove_query_param(current_query, 'category'),
        })
    if department:
        dept_name = Department.objects.filter(id=department).values_list('name', flat=True).first()
        active_tags.append({
            'label': f"Department: {dept_name or department}",
            'remove_query': _remove_query_param(current_query, 'department'),
        })
    if participation:
        active_tags.append({
            'label': f"Participation: {participation.title()}",
            'remove_query': _remove_query_param(current_query, 'participation'),
        })
    if start_date or end_date:
        active_tags.append({
            'label': f"Date: {start_date or '...'} to {end_date or '...'}",
            'remove_query': _remove_query_param(
                _remove_query_param(current_query, 'start_date'),
                'end_date'
            ),
        })
    context['active_filter_tags'] = active_tags

    if _is_ajax_request(request):
        return render(request, 'events/partials/view_all_events_list.html', context)

    return render(request, 'events/view_all_events.html', context)


@login_required(login_url='/login/')
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

    events = events.select_related('created_by', 'department', 'venue').order_by('-start_date')

    search = request.GET.get('search', '')
    legacy_hashtag = request.GET.get('hashtag', '')
    text_query, hashtag_filters = _parse_search_and_hashtags(search, legacy_hashtag)
    events = _apply_event_search(events, text_query)
    if hashtag_filters:
        events = events.filter(hashtags__name__in=hashtag_filters).distinct()

    quick = request.GET.get('quick', 'all')
    if quick not in {'all', 'completed', 'verified', 'upcoming'}:
        quick = 'all'
    events = _apply_quick_filter(events, quick)

    # 📌 Status filter
    status = request.GET.get('status')
    if status is None:
        events = events.filter(status__in=['completed', 'verified'])
        selected_status = "conducted"

    elif status == "conducted":
        events = events.filter(status__in=['completed', 'verified'])
        selected_status = "conducted"

    else:
        events = events.filter(status=status)
        selected_status = status

    # 👥 Participation filter
    participation = _normalize_filter_value(request.GET.get('participation'))
    if participation:
        events = events.filter(participation_type=participation)

    # 📅 Date range filter (UPDATED)
    start_date = _normalize_filter_value(request.GET.get('start_date'))
    end_date = _normalize_filter_value(request.GET.get('end_date'))

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
        'selected_status': selected_status,
        'quick': quick,
        'selected_participation': participation,
        'search_value': _normalize_filter_value(search),
        'start_date_value': start_date,
        'end_date_value': end_date,
        'active_filter_tags': [],
        'current_query': request.GET.copy(),
        'active_nav': 'faculty-filter',
    }

    active_tags = []
    current_query = request.GET.copy()
    if search.strip():
        active_tags.append({
            'label': f"Search: {search.strip()}",
            'remove_query': _remove_query_param(current_query, 'search'),
        })
    if quick != 'all':
        active_tags.append({
            'label': f"Quick: {quick.title()}",
            'remove_query': _remove_query_param(current_query, 'quick'),
        })
    if status and status != "conducted":
        active_tags.append({
            'label': f"Status: {status.title()}",
            'remove_query': _remove_query_param(current_query, 'status'),
        })
    if participation:
        active_tags.append({
            'label': f"Participation: {participation.title()}",
            'remove_query': _remove_query_param(current_query, 'participation'),
        })
    if start_date or end_date:
        active_tags.append({
            'label': f"Date: {start_date or '...'} to {end_date or '...'}",
            'remove_query': _remove_query_param(
                _remove_query_param(current_query, 'start_date'),
                'end_date'
            ),
        })
    context['active_filter_tags'] = active_tags

    if _is_ajax_request(request):
        return render(request, 'events/partials/faculty_filter_list.html', context)

    return render(request, 'events/faculty_filter.html', context)


@login_required(login_url='/login/')
def faculty_post_submission_due_events(request):
    if request.user.role != 'faculty':
        return redirect('login')

    events = Event.objects.filter(
        created_by=request.user,
        status='approved'
    ).select_related('created_by', 'department', 'venue').order_by('-start_date')

    return render(
        request,
        'events/faculty_post_submission_due.html',
        {
            'events': events,
            'active_nav': 'faculty-post-submissions',
        }
    )


@login_required(login_url='/login/')
def faculty_approved_events(request):
    if request.user.role != 'faculty':
        return redirect('login')

    events = Event.objects.filter(
        created_by=request.user,
        status='approved',
    ).select_related('created_by', 'department', 'venue').order_by('-start_date')

    return render(
        request,
        'events/faculty_approved_events.html',
        {
            'events': events,
            'active_nav': 'faculty-approved',
        }
    )


@login_required(login_url='/login/')
def faculty_upload_post_event_data(request):
    if request.user.role != 'faculty':
        return redirect('login')

    events = Event.objects.filter(
        created_by=request.user,
        status='approved',
        end_date__lt=timezone.localdate(),
    ).select_related('created_by', 'department', 'venue').order_by('-start_date')

    return render(
        request,
        'events/faculty_upload_post_event_data.html',
        {
            'events': events,
            'active_nav': 'faculty-post-upload',
        }
    )


@login_required(login_url='/login/')
def faculty_rejected_events(request):
    if request.user.role != 'faculty':
        return redirect('login')

    events = Event.objects.filter(
        created_by=request.user,
        status='rejected'
    ).select_related('created_by', 'department', 'venue').order_by('-created_at')

    return render(
        request,
        'events/faculty_rejected_events.html',
        {
            'events': events,
            'active_nav': 'faculty-rejected',
        }
    )


@login_required(login_url='/login/')
def faculty_edit_resubmit_event(request, event_id):
    if request.user.role != 'faculty':
        return redirect('login')

    event = get_object_or_404(Event, id=event_id, created_by=request.user)
    if event.status != 'rejected':
        messages.error(request, "Only rejected events can be edited and resubmitted.")
        return redirect('event_detail', event_id=event.id)

    if request.method == "POST":
        form = EventForm(request.POST, instance=event, user=request.user)
        if form.is_valid():
            updated_event = form.save(commit=False)
            updated_event.status = 'pending'
            updated_event.principal_remark = ''
            updated_event.save()

            principal = User.objects.filter(role='principal').first()
            if principal:
                notify(
                    recipient=principal,
                    sender=request.user,
                    event=updated_event,
                    type='submitted',
                    message=f"Event '{updated_event.title}' was edited and resubmitted for approval."
                )

            messages.success(request, "Event updated and resubmitted for approval.")
            return redirect('faculty_rejected_events')
    else:
        form = EventForm(instance=event, user=request.user)

    return render(
        request,
        'events/faculty_edit_resubmit.html',
        {
            'form': form,
            'event': event,
            'active_nav': 'faculty-rejected',
        }
    )


@login_required(login_url='/login/')
def principal_approved_events(request):

    if request.user.role != 'principal':
        return redirect('login')

    today = timezone.now().date()

    approved_events = Event.objects.filter(
        status='approved'
    ).order_by('-start_date')

    context = {
        'approved_events': approved_events,
        'today': today,
        'active_nav': 'principal-approved',
    }

    return render(
        request,
        'events/principal_approved.html',
        context
    )


@login_required(login_url='/login/')
def change_event_venue(request, event_id):

    if request.user.role != 'principal':
        return redirect('login')

    event = get_object_or_404(Event, id=event_id)

    if event.status != 'approved':
        messages.error(request, "Venue can only be changed for approved events.")
        return redirect('principal_approved_events')

    today = timezone.now().date()
    if event.end_date < today:
        messages.error(request, "Cannot change venue. Event has already ended.")
        return redirect('principal_approved_events')

    class VenueUpdateForm(forms.ModelForm):
        class Meta:
            model = Event
            fields = ['venue']

    if request.method == 'POST':
        form = VenueUpdateForm(request.POST, instance=event)

        if form.is_valid():
            selected_venue = form.cleaned_data['venue']

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

                # Reload clean form from database
                event.refresh_from_db()
                form = VenueUpdateForm(instance=event)

                return render(
                    request,
                    'events/change_venue.html',
                    {
                        'form': form,
                        'event': event,
                        'active_nav': 'principal-approved',
                    }
                )

            form.save()
            notify(
                recipient=event.created_by,
                sender=request.user,
                event=event,
                type='venue_changed',
                message=f"Venue changed for '{event.title}'. New venue: {event.venue}"
            )
            messages.success(request, "Venue updated successfully.")
            return redirect('principal_approved_events')

    else:
        form = VenueUpdateForm(instance=event)

    return render(
        request,
        'events/change_venue.html',
        {
            'form': form,
            'event': event,
            'active_nav': 'principal-approved',
        }
    )


@login_required(login_url='/login/')
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

@login_required(login_url='/login/')
def event_detail(request, event_id):

    event = get_object_or_404(Event, id=event_id)

    return render(request,
                  'events/event_detail.html',
                  {'event': event})


@login_required(login_url='/login/')
def principal_rejected_events(request):

    if request.user.role != 'principal':
        return redirect('login')

    rejected_events = Event.objects.filter(status='rejected').order_by('-created_at')

    return render(
        request,
        'events/principal_rejected.html',
        {
            'rejected_events': rejected_events,
            'active_nav': 'principal-rejected',
        }
    )





def download_detailed_report(request, event_id):

    event = get_object_or_404(Event, id=event_id)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="{event.title}_Detailed_Report.pdf"'
    )

    doc = SimpleDocTemplate(response, pagesize=A4)
    elements = []

    styles = getSampleStyleSheet()

    # ---- Title ----
    title_style = styles["Heading1"]
    title_style.alignment = TA_CENTER
    elements.append(Paragraph("DETAILED EVENT REPORT", title_style))
    elements.append(Spacer(1, 20))

    # ---- Basic Details ----
    details = f"""
    <b>Event Title:</b> {event.title}<br/>
    <b>Department:</b> {event.department}<br/>
    <b>Venue:</b> {event.venue}<br/>
    <b>Date:</b> {event.start_date} to {event.end_date}<br/>
    <b>Chief Guest:</b> {event.chief_guest if event.chief_guest else "N/A"}<br/>
    """

    elements.append(Paragraph(details, styles["Normal"]))
    elements.append(Spacer(1, 20))

    # ---- Report Text ----
    elements.append(Paragraph("<b>Event Description:</b>", styles["Heading3"]))
    elements.append(Spacer(1, 10))

    report_text = event.report_text if event.report_text else "No report available."
    elements.append(
        Paragraph(report_text.replace("\n", "<br/>"), styles["Normal"])
    )
    elements.append(Spacer(1, 20))

    # ---- Photos Section ----
    elements.append(Paragraph("<b>Event Photos:</b>", styles["Heading3"]))
    elements.append(Spacer(1, 10))

    for photo in event.photos.all():
        image_path = photo.image.path
        if os.path.exists(image_path):
            img = Image(image_path, width=4 * inch, height=3 * inch)
            elements.append(img)
            elements.append(Spacer(1, 15))

    # ---- Footer ----
    elements.append(Spacer(1, 30))
    elements.append(
        Paragraph(
            f"Generated on {datetime.now().strftime('%d %B %Y, %I:%M %p')}",
            styles["Normal"]
        )
    )

    doc.build(elements)

    return response


@never_cache
@login_required(login_url='/login/')
def search_events(request):
    query = request.GET.get('q', '')
    hashtag = request.GET.get('hashtag', '').strip().lstrip('#').lower()

    events = Event.objects.filter(
        Q(title__icontains=query) |
        Q(category__icontains=query) |
        Q(department__name__icontains=query) |
        Q(venue__name__icontains=query) |
        Q(hashtags__name__icontains=query)
    ).select_related('department').order_by('-start_date').distinct()

    if hashtag:
        events = events.filter(hashtags__name=hashtag)

    data = []
    for event in events:
        data.append({
            "id": event.id,
            "title": event.title,
            "category": event.category,
            "department": event.department.name if event.department else "General",
            "status": event.status,
            "hashtags": [tag.name for tag in event.hashtags.order_by('name')],
        })

    return JsonResponse({"events": data})
