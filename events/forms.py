from django import forms
from .models import Event


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        exclude = ['created_by', 'status', 'principal_remark', 'created_at']