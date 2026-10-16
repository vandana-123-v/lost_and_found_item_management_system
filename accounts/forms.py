from django import forms
from django.contrib.auth.forms import UserCreationForm
from core.uploads import validate_image
from .models import User


class UserFieldsMixin:
    def clean_email(self):
        value = self.cleaned_data["email"].strip().lower()
        qs = User.objects.filter(email__iexact=value)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("This email is already registered.")
        return value

    def clean_username(self):
        value = self.cleaned_data["username"].strip().lower()
        qs = User.objects.filter(username__iexact=value)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("This username is already registered.")
        return value


class RegisterForm(UserFieldsMixin, UserCreationForm):
    terms = forms.BooleanField(label="I accept the terms and privacy notice.")

    class Meta:
        model = User
        fields = [
            "full_name",
            "username",
            "email",
            "phone",
            "password1",
            "password2",
            "terms",
        ]


class LoginForm(forms.Form):
    username = forms.CharField(label="Username or email", max_length=254)
    password = forms.CharField(widget=forms.PasswordInput)
    remember = forms.BooleanField(required=False, label="Remember me for 14 days")


class ProfileForm(UserFieldsMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ["full_name", "username", "email", "phone", "avatar"]

    def clean_avatar(self):
        value = self.cleaned_data.get("avatar")
        if value and hasattr(value, "content_type"):
            validate_image(value)
        return value
