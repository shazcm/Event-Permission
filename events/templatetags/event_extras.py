from django import template

register = template.Library()

@register.filter
def format_event_datetime(event):

    if not event.start_date or not event.end_date:
        return ""

    # Format date part
    if event.start_date == event.end_date:
        date_part = event.start_date.strftime("%d %b %Y")
    else:
        date_part = f"{event.start_date.strftime('%d %b %Y')} – {event.end_date.strftime('%d %b %Y')}"

    # Format time part (if exists)
    if event.start_time and event.end_time:
        time_part = f"{event.start_time.strftime('%I:%M %p')} – {event.end_time.strftime('%I:%M %p')}"
        return f"{date_part} | {time_part}"

    return date_part