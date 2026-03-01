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
from django.http import JsonResponse
from datetime import datetime
from django.utils import timezone
from .models import EventPhoto
from .forms import EventPhotoForm
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from django.http import HttpResponse
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.platypus import ListFlowable, ListItem
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER
import os



@login_required
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

@login_required
def post_event_upload(request, event_id):

    event = get_object_or_404(Event, id=event_id)

    # Only event creator can access
    if event.created_by != request.user:
        return redirect('faculty_dashboard')

    if request.method == "POST":

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
            return redirect('faculty_dashboard')

        event.save()

    return render(request, 'events/post_upload.html', {
        'event': event
    })

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

    event = get_object_or_404(Event, id=event_id)

    if request.method == "POST" and event.status == "completed":
        event.status = 'verified'
        event.save()

    return redirect('event_detail', event_id=event.id)


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

    events = Event.objects.filter(
    status__in=['completed', 'verified']
    ).order_by('-start_date')

    # 🔎 Search by title
    search = request.GET.get('search')
    if search:
        events = events.filter(title__icontains=search)


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


@login_required
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
                    {'form': form, 'event': event}
                )

            form.save()
            messages.success(request, "Venue updated successfully.")
            return redirect('principal_approved_events')

    else:
        form = VenueUpdateForm(instance=event)

    return render(
        request,
        'events/change_venue.html',
        {'form': form, 'event': event}
    )


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

@login_required
def event_detail(request, event_id):

    event = get_object_or_404(Event, id=event_id)

    return render(request,
                  'events/event_detail.html',
                  {'event': event})





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