from django import forms
from .models import Event
from .models import EventPhoto

class EventForm(forms.ModelForm):

    class Meta:
        model = Event
        fields = [
            'title',
            'start_date',
            'end_date',
            'start_time',
            'end_time',
            'chief_guest',
            'venue',
            'department',
            'participation_type',
            'budget',
            'description',
        ]

        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user:
            self.fields['department'].widget=forms.HiddenInput()
            if 'category' in self.fields:
                    self.fields['category'].widget=forms.HiddenInput()

    # ✅ Time validation
    def clean(self):
        cleaned_data = super().clean()

        start = cleaned_data.get('start_time')
        end = cleaned_data.get('end_time')

        if start and end:
            if start >= end:
                self.add_error('end_time', "End time must be after start time.")
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date:
            if start_date > end_date:
                self.add_error('end_date', "End date must be after start date.")

        return cleaned_data


class PostEventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = [ 'attendance_file', 'completed_at']

class EventPhotoForm(forms.ModelForm):
    class Meta:
        model = EventPhoto
        fields = ['image']
