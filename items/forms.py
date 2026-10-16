from django import forms
from django.utils import timezone
from core.uploads import validate_image
from .models import Item, Category


class MultipleImageInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.FileField):
    widget = MultipleImageInput

    def clean(self, data, initial=None):
        data = data if isinstance(data, (list, tuple)) else [data] if data else []
        if len(data) > 6:
            raise forms.ValidationError("Upload up to six images.")
        return [
            validate_image(super(MultipleImageField, self).clean(value, initial))
            for value in data
        ]


class ItemForm(forms.ModelForm):
    images = MultipleImageField(
        required=False,
        help_text="Up to 6 images, 5 MB each. JPG, PNG, WEBP. Images are visible to other members after approval; keep secret marks out of photos.",
        widget=MultipleImageInput(
            attrs={"accept": "image/jpeg,image/png,image/webp", "class": "image-upload"}
        ),
    )

    class Meta:
        model = Item
        fields = [
            "title",
            "description",
            "category",
            "brand",
            "model",
            "primary_color",
            "secondary_color",
            "event_date",
            "event_time",
            "location",
            "detailed_location",
            "private_identifying_details",
            "serial_number",
            "contact_information",
            "holding_location",
            "additional_notes",
        ]
        widgets = {
            "event_date": forms.DateInput(attrs={"type": "date"}),
            "event_time": forms.TimeInput(attrs={"type": "time"}),
            "description": forms.Textarea(attrs={"rows": 4}),
            "private_identifying_details": forms.Textarea(attrs={"rows": 3}),
            "additional_notes": forms.Textarea(attrs={"rows": 2}),
        }
        help_texts = {
            "description": "Visible to members. Do not include secrets or personal contact details.",
            "private_identifying_details": "Private: visible only to you and administrators.",
            "serial_number": "Private ownership verification evidence.",
            "detailed_location": "Private: precise location is shared only with administrators.",
            "contact_information": "Private: for administrator contact only.",
            "holding_location": "Private: where staff can collect the item.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(active=True)

    def clean_event_date(self):
        value = self.cleaned_data["event_date"]
        if value > timezone.localdate():
            raise forms.ValidationError("The event date cannot be in the future.")
        return value


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "active"]
