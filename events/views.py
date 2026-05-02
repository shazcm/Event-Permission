from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Count, Q
from django.utils import timezone
from django import forms
from datetime import datetime
import os

from .forms import EventForm, PostEventForm, EventPhotoForm
from .models import Event, Department, Tag, Venue, EventPhoto

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.platypus import ListFlowable, ListItem
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER

from accounts.utils import notify
from accounts.models import User, Notification


def _is_ajax_request(request):
    return (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or request.GET.get("ajax") == "1"
    )


def _apply_event_search(queryset, query):

    if not query:
        return queryset

    # Hashtag search
    if query.startswith("#"):

        tag_name = query[1:].strip().lower()

        return queryset.filter(
            tags__name__iexact=tag_name,
            status__in=["completed","verified"]
        ).distinct()

    # Normal search
    return queryset.filter(
        Q(title__icontains=query) |
        Q(description__icontains=query) |
        Q(category__icontains=query) |
        Q(participation_type__icontains=query) |
        Q(status__icontains=query) |
        Q(department__name__icontains=query) |
        Q(venue__name__icontains=query) |
        Q(created_by__username__icontains=query) |
        Q(created_by__first_name__icontains=query) |
        Q(created_by__last_name__icontains=query) |
        Q(tags__name__icontains=query)
    ).distinct()



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
def tag_autocomplete(request):

    query = request.GET.get("q")

    if not query:
        return JsonResponse([], safe=False)

    tags = Tag.objects.filter(name__icontains=query)[:10]

    data = list(tags.values_list("name", flat=True))

    return JsonResponse(data, safe=False)

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

        # ✅ Allow rejection for both pending & approved
        if event.status not in ['pending', 'approved']:
            messages.error(request, "Only pending or approved events can be rejected.")
            return redirect('principal_pending_events')

        remark = request.POST.get('remark')

        # ❗ Make reason mandatory
        if not remark or remark.strip() == "":
            messages.error(request, "Rejection reason is required.")
            return redirect(request.META.get('HTTP_REFERER'))

        event.status = 'rejected'
        event.principal_remark = remark.strip()
        
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

    return redirect(request.META.get('HTTP_REFERER', 'principal_pending_events'))



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

    if event.status == 'cancelled':
        messages.error(request, "This event has been cancelled.")
        return redirect('faculty_dashboard')

    # Only event creator can access
    if event.created_by != request.user:
        return redirect('faculty_dashboard')
    
    today = timezone.now().date()

    if event.end_date > today:
        messages.error(request, "You can upload post-event details only after the event is completed.")
        return redirect('faculty_dashboard')

    if request.method == "POST":

        # ---- Handle Attendance Upload ----
        if request.FILES.get('attendance_file'):
            event.attendance_file = request.FILES.get('attendance_file')
            event.save()  # Save attendance immediately so it's not lost

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

            # Handle tags submitted with the report
            tags_input = request.POST.get("tags_input", "").strip()
            if tags_input:
                event.tags.clear()
                for tag_name in tags_input.split(","):
                    tag_name = tag_name.strip().lower().lstrip("#")
                    if tag_name:
                        tag, _ = Tag.objects.get_or_create(name=tag_name)
                        event.tags.add(tag)

            event.save()

            principal = User.objects.filter(role='principal').first()
            if principal:
                notify(
                    recipient=principal,
                    sender=request.user,
                    event=event,
                    type='completed',
                    message=f"Event '{event.title}' marked as completed. Please verify."
                )
            return redirect('faculty_dashboard')

        event.save()

    return render(request, 'events/post_upload.html', {
        'event': event,
        'active_nav': 'faculty-dashboard',
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

    from datetime import date, timedelta
    from dateutil.relativedelta import relativedelta

    all_events = Event.objects.select_related('department', 'venue', 'created_by')
    today = date.today()

    # ── Status counts ──────────────────────────────────────────────
    total_events = all_events.count()
    pending   = all_events.filter(status='pending').count()
    approved  = all_events.filter(status='approved').count()
    completed = all_events.filter(status='completed').count()
    verified  = all_events.filter(status='verified').count()
    rejected  = all_events.filter(status='rejected').count()
    cancelled = all_events.filter(status='cancelled').count()

    decided = approved + completed + verified + rejected + cancelled
    approval_rate = round((approved + completed + verified) / decided * 100) if decided else 0

    # Percentage of each status relative to total events (for donut legend)
    def pct(count):
        return round(count / total_events * 100) if total_events else 0

    approved_pct  = pct(approved)
    pending_pct   = pct(pending)
    rejected_pct  = pct(rejected)
    verified_pct  = pct(verified)
    completed_pct = pct(completed)
    cancelled_pct = pct(cancelled)

    # ── Monthly submission activity (last 12 months) ───────────────
    month_names = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    monthly_labels, monthly_counts = [], []
    peak_month_label, peak_month_count = '', 0
    total_last_12 = 0
    for i in range(11, -1, -1):
        d = today - relativedelta(months=i)
        label = month_names[d.month - 1]
        cnt = all_events.filter(start_date__year=d.year, start_date__month=d.month, status__in=['completed', 'verified']).count()
        monthly_labels.append(label)
        monthly_counts.append(cnt)
        total_last_12 += cnt
        if cnt > peak_month_count:
            peak_month_count = cnt
            peak_month_label = month_names[d.month - 1]

    avg_per_month = round(total_last_12 / 12, 1)
    quiet_months = sum(1 for c in monthly_counts if c == 0)
    above_avg_months = sum(1 for c in monthly_counts if c > avg_per_month)

    # Days since last conducted event
    last_conducted = all_events.filter(
        status__in=['completed', 'verified'],
        completed_at__isnull=False
    ).order_by('-completed_at').first()
    if last_conducted:
        days_since_last = (today - last_conducted.completed_at.date()).days
    else:
        days_since_last = None

    # Avg turnaround: days between created_at and completed_at for completed/verified events
    from django.db.models import Avg, F, ExpressionWrapper, DurationField
    turnaround_qs = all_events.filter(
        status__in=['completed', 'verified'],
        completed_at__isnull=False
    ).annotate(
        duration=ExpressionWrapper(F('completed_at') - F('created_at'), output_field=DurationField())
    ).aggregate(avg_dur=Avg('duration'))
    avg_turnaround_days = '-'
    if turnaround_qs['avg_dur']:
        avg_turnaround_days = str(turnaround_qs['avg_dur'].days) + ' days'

    # ── Department activity ────────────────────────────────────────
    dept_data = list(
        all_events.values('department__name')
        .annotate(count=Count('id'))
        .order_by('-count')[:6]
    )
    max_dept = max((d['count'] for d in dept_data), default=1)
    dept_rows = [{
        'name': d['department__name'] or 'General',
        'count': d['count'],
        'pct': round(d['count'] / max_dept * 100),
    } for d in dept_data]

    # ── Venue utilisation ──────────────────────────────────────────
    venue_data = list(
        all_events.values('venue__name')
        .annotate(count=Count('id'))
        .order_by('-count')[:6]
    )
    top_venue = venue_data[0]['venue__name'] if venue_data else '-'
    venue_rows = [{'name': v['venue__name'] or 'Unknown', 'count': v['count']} for v in venue_data]

    # ── Participation type ─────────────────────────────────────────
    boys  = all_events.filter(participation_type='boys').count()
    girls = all_events.filter(participation_type='girls').count()
    mixed = all_events.filter(participation_type='mixed').count()

    # ── Faculty leaderboard ────────────────────────────────────────
    faculty_data = list(
        all_events
        .values('created_by__first_name', 'created_by__last_name', 'created_by__username')
        .annotate(count=Count('id'))
        .order_by('-count')[:5]
    )
    max_faculty = max((f['count'] for f in faculty_data), default=1)
    faculty_rows = []
    for f in faculty_data:
        full = (f['created_by__first_name'] + ' ' + f['created_by__last_name']).strip()
        faculty_rows.append({
            'name': full or f['created_by__username'],
            'count': f['count'],
            'pct': round(f['count'] / max_faculty * 100),
        })

    context = {
        'total': total_events,
        'pending': pending,
        'approved': approved,
        'completed': completed,
        'verified': verified,
        'rejected': rejected,
        'cancelled': cancelled,
        'approval_rate': approval_rate,
        'approved_pct': approved_pct,
        'pending_pct': pending_pct,
        'rejected_pct': rejected_pct,
        'verified_pct': verified_pct,
        'completed_pct': completed_pct,
        'cancelled_pct': cancelled_pct,

        # submission activity chart
        'monthly_labels': monthly_labels,
        'monthly_counts': monthly_counts,
        'peak_month_label': peak_month_label,
        'peak_month_count': peak_month_count,
        'avg_per_month': avg_per_month,
        'avg_turnaround_days': avg_turnaround_days,
        'quiet_months': quiet_months,
        'total_last_12': total_last_12,
        'days_since_last': days_since_last,
        'above_avg_months': above_avg_months,

        # status donut
        'status_labels': ['Approved', 'Pending', 'Verified', 'Completed', 'Rejected', 'Cancelled'],
        'status_counts': [approved, pending, verified, completed, rejected, cancelled],

        # dept
        'dept_rows': dept_rows,

        # venue
        'venue_rows': venue_rows,
        'top_venue': top_venue,

        # participation
        'boys': boys,
        'girls': girls,
        'mixed': mixed,
        'participation_labels': ['Boys', 'Girls', 'Mixed'],
        'participation_counts': [boys, girls, mixed],

        # faculty
        'faculty_rows': faculty_rows,

        'active_nav': 'principal-analytics',
    }

    return render(request, 'events/analytics.html', context)


@login_required(login_url='/login/')
def view_all_events(request):

    if request.user.role != 'principal':
        return redirect('login')

    events = Event.objects.all(
    ).select_related('created_by', 'department', 'venue').order_by('-start_date')

    # 🔎 Search
    search = request.GET.get('search', '').strip()
    events = _apply_event_search(events, search)


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

    show_verified = request.GET.get('verified')

    if show_verified == "1":
        events = events.filter(status='verified')
        show_verified = True
    else:
        show_verified = False

    departments = Department.objects.all()

    context = {
        'events': events,
        'departments': departments,
        'show_verified': show_verified,
        'active_nav': 'principal-all',
    }

    if _is_ajax_request(request):
        return render(request, 'events/partials/view_all_events_list.html', context)

    return render(request, 'events/view_all_events.html', context)


@login_required(login_url='/login/')
def faculty_filter_events(request):

    if request.user.role != 'faculty':
        return redirect('login')

    user = request.user

    # Only show events created by this user
    events = Event.objects.filter(created_by=user)
    page_title = "My Events"
    total_count = events.count()

    events = events.select_related('created_by', 'department', 'venue').order_by('-start_date')

    # 🔎 Search
    search = request.GET.get('search', '').strip()
    events = _apply_event_search(events, search)

    # 📌 Status filter
    status = request.GET.get('status')
    upcoming = request.GET.get('upcoming')  # upcoming=1 means future approved events only

    if status is None or status == '':
        # No filter — show all
        selected_status = ''

    elif status == "conducted":
        events = events.filter(status__in=['completed', 'verified'])
        selected_status = "conducted"

    else:
        events = events.filter(status=status)
        selected_status = status

    # 📅 Upcoming: restrict to future start dates when upcoming=1
    if upcoming == '1':
        today_date = timezone.now().date()
        events = events.filter(start_date__gte=today_date)
        page_title = "Upcoming Events"
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
        'selected_status': selected_status,
        'total_count': total_count,
        'today': timezone.now().date(),
        'active_nav': 'faculty-filter',
    }

    if _is_ajax_request(request):
        return render(request, 'events/partials/faculty_filter_list.html', context)

    return render(request, 'events/faculty_filter.html', context)


@login_required(login_url='/login/')
def principal_approved_events(request):

    if request.user.role != 'principal':
        return redirect('login')

    today = timezone.now().date()

    approved_events = Event.objects.filter(
        status='approved',
        end_date__gte=today  # only events that haven't ended yet
    ).order_by('start_date')  # nearest first

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

    if event.status == 'cancelled':
        messages.error(request, "This event has been cancelled.")
        return redirect('faculty_dashboard')

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

    # Faculty can only view their own events
    if request.user.role == 'faculty' and event.created_by != request.user:
        messages.error(request, "You do not have permission to view this event.")
        return redirect('faculty_dashboard')

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





@login_required(login_url='/login/')
def download_detailed_report(request, event_id):

    event = get_object_or_404(Event, id=event_id)

    # Only the event creator (faculty) or the principal can download
    if request.user.role == 'faculty' and event.created_by != request.user:
        messages.error(request, "You do not have permission to download this report.")
        return redirect('faculty_dashboard')

    if request.user.role not in ('faculty', 'principal'):
        return redirect('login')

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

    events = Event.objects.filter(
        Q(title__icontains=query) |
        Q(category__icontains=query) |
        Q(department__name__icontains=query) |
        Q(venue__name__icontains=query)
    ).filter(
        status__in=['approved', 'completed', 'verified']
    ).select_related('department').order_by('-start_date')

    data = []
    for event in events:
        data.append({
            "id": event.id,
            "title": event.title,
            "category": event.category,
            "department": event.department.name if event.department else "General",
            "status": event.status,
        })

    return JsonResponse({"events": data})

@login_required(login_url='/login/')
def cancel_event(request, event_id):

    event = get_object_or_404(Event, id=event_id)

    # ✅ BLOCK PAST EVENTS
    if event.end_date < timezone.now().date():
        messages.error(request, "Past events cannot be cancelled.")
        return redirect('faculty_dashboard')

    # Only creator can cancel
    if event.created_by != request.user:
        return redirect('faculty_dashboard')

    # Allow only pending or approved
    if event.status not in ['pending', 'approved']:
        messages.error(request, "This event cannot be cancelled.")
        return redirect('faculty_dashboard')

    # 🔴 Save old status BEFORE change
    old_status = event.status

    # ✅ Remove "submitted" notification if event was still pending
    if old_status == 'pending':
        Notification.objects.filter(
            event=event,
            type='submitted'
        ).delete()

    # Update status
    event.status = 'cancelled'
    event.save()

    # 🔔 Notify ONLY if it was approved
    if old_status == 'approved':
        principal = User.objects.filter(role='principal').first()

        if principal:
            notify(
                recipient=principal,
                sender=request.user,
                event=event,
                type='cancelled',
                message=f"Approved event '{event.title}' was cancelled by faculty."
            )

    messages.success(request, "Event cancelled successfully.")

    return redirect('faculty_dashboard')

@login_required(login_url='/login/')
def faculty_post_due_events(request):
    """Events that are approved and past their end date — due for post-event upload."""
    if request.user.role != 'faculty':
        return redirect('login')

    today = timezone.now().date()
    events = Event.objects.filter(
        created_by=request.user,
        status='approved',
        end_date__lt=today
    ).order_by('end_date')

    return render(request, 'events/faculty_post_due_events.html', {
        'events': events,
        'today': today,
        'active_nav': 'faculty-post-due',
    })


@login_required(login_url='/login/')
def edit_event(request, event_id):

    event = get_object_or_404(Event, id=event_id)

    # Only creator can edit
    if event.created_by != request.user:
        return redirect('faculty_dashboard')

    # Allow only rejected events
    if event.status != 'rejected':
        messages.error(request, "Only rejected events can be edited.")
        return redirect('faculty_dashboard')

    if request.method == "POST":
        form = EventForm(request.POST, instance=event, user=request.user)

        if form.is_valid():
            event = form.save(commit=False)

            # 🔁 Reset status
            event.status = 'pending'
            event.principal_remark = ''

            event.save()
            form.save_m2m()

            # 🔔 Notify principal again
            principal = User.objects.filter(role='principal').first()
            if principal:
                notify(
                    recipient=principal,
                    sender=request.user,
                    event=event,
                    type='submitted',
                    message=f"Event '{event.title}' has been resubmitted after changes."
                )

            messages.success(request, "Event updated and resubmitted.")
            return redirect('faculty_dashboard')

    else:
        form = EventForm(instance=event, user=request.user)

    return render(request, 'events/edit_event.html', {
        'form': form,
        'event': event
    })