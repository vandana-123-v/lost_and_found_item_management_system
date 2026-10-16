from django import forms
from django.conf import settings
from core.uploads import validate_image
from items.models import Category


class ImageSearchForm(forms.Form):
    image = forms.ImageField(
        label="Photo of your lost item",
        validators=[validate_image],
        widget=forms.FileInput(
            attrs={"accept": "image/jpeg,image/png,image/webp", "class": "image-upload"}
        ),
        help_text="JPG, PNG or WEBP, up to 5 MB. Choose a clear photo of the object, not a person.",
    )
    category = forms.ModelChoiceField(
        queryset=Category.objects.filter(active=True),
        required=False,
        empty_label="All categories",
    )
    location = forms.CharField(
        max_length=200,
        required=False,
        help_text="Optional: narrow the search to a general location.",
    )
    consent = forms.BooleanField(
        label="Consent for this search"
        if getattr(settings, "CLIP_ENABLED", False)
        else "Send this image to Google Gemini to search for similar found items.",
        help_text=(
            "This photo is used for the search only and is not saved as a report."
            if getattr(settings, "CLIP_ENABLED", False)
            else "The search photo is used for this request and is not saved as a report."
        ),
    )

    def clean_image(self):
        if hasattr(self.files, "getlist") and len(self.files.getlist("image")) != 1:
            raise forms.ValidationError("Choose exactly one search photo.")
        return self.cleaned_data["image"]
