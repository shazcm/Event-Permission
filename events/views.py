from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .forms import EventForm
from .models import Event, Department
from django.utils import timezone
from .forms import PostEventForm
from django.db.models import Count

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

    category = request.GET.get('category')
    department = request.GET.get('department')
    status = request.GET.get('status')

    if category:
        events = events.filter(category=category)

    if department:
        events = events.filter(department_id=department)

    if status:
        events = events.filter(status=status)

    departments = Department.objects.all()

    context = {
        'events': events,
        'departments': departments,
    }

    return render(request,
                  'events/filter_events.html',
                  context)