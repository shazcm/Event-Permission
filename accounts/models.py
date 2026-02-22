from django.contrib.auth.models import AbstractUser
from django.db import models

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