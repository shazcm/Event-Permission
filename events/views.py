from django.db.models import Sum
from django.db.models import Count
from django.db.models.functions import TruncMonth
from datetime import datetime, timedelta
from django.utils import timezone
from django.db import models
from django.db.models import Sum, Count
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .forms import EventForm
from .models import Event
from django.utils import timezone
from .forms import PostEventForm
from django.db.models import Count

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


@login_required
def principal_pending_events(request):

    if request.user.role != 'principal':
        return redirect('login')

    events = Event.objects.filter(status='pending').order_by('-created_at')

    # 🔎 Get filter values
    category = request.GET.get('category')
    department = request.GET.get('department')
    search = request.GET.get('search')

    if category:
        events = events.filter(category=category)

    if department:
        events = events.filter(department=department)

    if search:
        events = events.filter(title__icontains=search)

    # Stats
    total_pending = events.count()
    total_budget = events.aggregate(total=Sum('budget'))['total'] or 0
    total_departments = events.values('department').distinct().count()

    # Dynamic dropdown data
    categories = Event.objects.values_list('category', flat=True).distinct()
    departments = Event.objects.values_list('department', flat=True).distinct()

    context = {
        'events': events,
        'total_pending': total_pending,
        'total_budget': total_budget,
        'total_departments': total_departments,
        'categories': categories,
        'departments': departments,
        'selected_category': category,
        'selected_department': department,
        'search_query': search,
    }

    return render(request, 'events/principal_pending.html', context)

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

    total = Event.objects.count()
    pending = Event.objects.filter(status='pending').count()
    approved = Event.objects.filter(status='approved').count()
    completed = Event.objects.filter(status='completed').count()
    verified = Event.objects.filter(status='verified').count()

    # 🔹 Completion Rate
    completion_rate = 0
    if total > 0:
        completion_rate = round((completed / total) * 100)

    # 🔹 Active Departments
    active_departments = Event.objects.values('department').distinct().count()

    # 🔹 This Month Events
    now = timezone.now()
    this_month = Event.objects.filter(
        created_at__year=now.year,
        created_at__month=now.month
    ).count()

    # 🔹 Monthly trend (last 6 months)
    six_months_ago = now - timedelta(days=180)

    monthly_data = (
        Event.objects
        .filter(created_at__gte=six_months_ago)
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(count=Count('id'))
        .order_by('month')
    )

    # Convert for template
    monthly_labels = []
    monthly_counts = []

    for item in monthly_data:
        monthly_labels.append(item['month'].strftime("%b"))
        monthly_counts.append(item['count'])

    # 🔹 Department performance
    department_data = (
        Event.objects
        .values('department')
        .annotate(
            total=Count('id'),
            pending=Count('id', filter=models.Q(status='pending')),
            completed=Count('id', filter=models.Q(status='completed')),
            verified=Count('id', filter=models.Q(status='verified'))
        )
        .order_by('-total')
    )

    context = {
        'total': total,
        'pending': pending,
        'approved': approved,
        'completed': completed,
        'verified': verified,
        'completion_rate': completion_rate,
        'active_departments': active_departments,
        'this_month': this_month,
        'monthly_labels': monthly_labels,
        'monthly_counts': monthly_counts,
        'department_data': department_data,
    }

    return render(request, 'events/analytics.html', context)

@login_required
def filter_events(request):

    if request.user.role != 'principal':
        return redirect('login')

    events = Event.objects.all()

    category = request.GET.get('category')
    department = request.GET.get('department')
    status = request.GET.get('status')

    if category:
        events = events.filter(category=category)

    if department:
        events = events.filter(department=department)

    if status:
        events = events.filter(status=status)

    return render(request,
                  'events/filter_events.html',
                  {'events': events})