from .models import Notification

def notify(recipient, sender, event, type, message):
    Notification.objects.create(
        recipient=recipient,
        sender=sender,
        event=event,
        type=type,
        message=message
    )