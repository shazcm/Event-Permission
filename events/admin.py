from django.contrib import admin
from .models import Event, Department, Venue, Hashtag

admin.site.register(Event)
admin.site.register(Department)
admin.site.register(Venue)
admin.site.register(Hashtag)
