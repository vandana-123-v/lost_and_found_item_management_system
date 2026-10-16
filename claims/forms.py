from django import forms
from django.utils import timezone
from core.uploads import validate_image
from .models import Claim


class ClaimForm(forms.ModelForm):
    class Meta:
        model = Claim
        fields = [
            "description",
            "ownership_evidence",
            "brand_model",
            "lost_location",
            "lost_date",
            "serial_number",
            "supporting_image",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "ownership_evidence": forms.Textarea(attrs={"rows": 4}),
            "lost_date": forms.DateInput(attrs={"type": "date"}),
        }
        help_texts = {
            "ownership_evidence": "Describe hidden markings, contents, purchase details, or other evidence only the owner would know.",
            "supporting_image": "Optional receipt or ownership photograph (JPG/PNG/WEBP, up to 5 MB). Only you and administrators can view this.",
        }

    def clean_lost_date(self):
        value = self.cleaned_data["lost_date"]
        if value > timezone.localdate():
            raise forms.ValidationError("Choose today or an earlier date.")
        return value

    def clean_ownership_evidence(self):
        value = self.cleaned_data["ownership_evidence"]
        if len(value.strip()) < 20:
            raise forms.ValidationError(
                "Provide at least 20 characters of meaningful ownership evidence."
            )
        return value

    def clean_supporting_image(self):
        value = self.cleaned_data.get("supporting_image")
        return validate_image(value) if value else value


class DecisionForm(forms.Form):
    status = forms.ChoiceField(choices=Claim.STATUSES)
    remarks = forms.CharField(
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Visible to the claimant. Do not reveal private verification secrets.",
    )
