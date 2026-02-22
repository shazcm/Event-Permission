from django import forms
from .models import Event


class EventForm(forms.ModelForm):

    class Meta:
        model = Event
        fields = [
            'title',
            'category',
            'department',
            'participation_type',
            'budget',
            'venue',
            'event_date',
            'description',
        ]

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user and user.sub_role == 'hod':
            self.fields['department'].widget = forms.HiddenInput()

class PostEventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ['report_text', 'attendance_file', 'photo']
