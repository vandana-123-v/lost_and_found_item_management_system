from django import forms
from accounts.models import User


class SendNotificationForm(forms.Form):
    recipient = forms.ModelChoiceField(queryset=User.objects.filter(is_active=True))
    title = forms.CharField(max_length=160)
    message = forms.CharField(max_length=3000, widget=forms.Textarea(attrs={"rows": 4}))
