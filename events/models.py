from django.db import models
from django.conf import settings


class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

class Venue(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name
    
class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name
    
class Event(models.Model):

    CATEGORY_CHOICES = (
        ('department', 'Department'),
        ('nss', 'NSS'),
        ('ncc', 'NCC'),
        ('union', 'Union'),
        ('other', 'Other'),
    )

    PARTICIPATION_CHOICES = (
        ('boys', 'Boys'),
        ('girls', 'Girls'),
        ('mixed', 'Mixed'),
    )

    STATUS_CHOICES = (
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('completed', 'Completed'),
        ('verified', 'Verified'),
    )

    title = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    department = models.ForeignKey(
    Department,
    on_delete=models.SET_NULL,
    null=True,
    blank=True
    )

    participation_type = models.CharField(
        max_length=20,
        choices=PARTICIPATION_CHOICES
    )
    chief_guest = models.CharField(max_length=200, blank=True, null=True)
    budget = models.DecimalField(max_digits=10, decimal_places=2)
    venue = models.ForeignKey(
    Venue,
    on_delete=models.PROTECT
    )

    start_date = models.DateField()
    end_date = models.DateField()
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)

    description = models.TextField()
    tags = models.ManyToManyField(Tag, blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )

    principal_remark = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    
    report_text = models.TextField(blank=True, null=True)

    attendance_file = models.FileField(
        upload_to='attendance/',
        blank=True,
        null=True
    )


    completed_at = models.DateTimeField(blank=True, null=True)


    def __str__(self):
        return self.title

class EventPhoto(models.Model):
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='photos'
    )
    image = models.ImageField(upload_to='event_photos/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Photo for {self.event.title}"