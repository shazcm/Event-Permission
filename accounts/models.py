from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
from events.models import Event

class User(AbstractUser):

    ROLE_CHOICES = (
        ('faculty', 'Faculty'),
        ('principal', 'Principal'),
        ('admin', 'Admin'),
    )

    SUB_ROLE_CHOICES = (
        ('hod', 'HOD'),
        ('nss', 'NSS In-Charge'),
        ('ncc', 'NCC In-Charge'),
        ('union', 'Union In-Charge'),
        ('other', 'Other In-Charge'),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    sub_role = models.CharField(
        max_length=20,
        choices=SUB_ROLE_CHOICES,
        blank=True,
        null=True
    )
    department = models.ForeignKey(
    'events.Department',
    on_delete=models.SET_NULL,
    null=True,
    blank=True
    )

    def __str__(self):
        return self.username


class Notification(models.Model):

    TYPE_CHOICES = (
        ('submitted', 'Event Submitted'),
        ('approved', 'Event Approved'),
        ('rejected', 'Event Rejected'),
        ('completed', 'Event Completed'),
        ('venue_changed', 'Venue Changed'),
        ('reminder', 'Reminder'),
    )

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications"
    )

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="sent_notifications"
    )

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    message = models.TextField()
    type = models.CharField(max_length=30, choices=TYPE_CHOICES)

    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.recipient.username} - {self.type}"