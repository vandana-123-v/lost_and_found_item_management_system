from django.conf import settings
from django.db import models
from django.urls import reverse
from core.uploads import upload_path


class Claim(models.Model):
    STATUSES = [
        (s, s.replace("_", " ").title())
        for s in [
            "PENDING",
            "UNDER_REVIEW",
            "APPROVED",
            "REJECTED",
            "RETURNED",
            "CANCELLED",
        ]
    ]
    item = models.ForeignKey(
        "items.Item", on_delete=models.PROTECT, related_name="claims"
    )
    claimant = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="claims"
    )
    description = models.TextField(max_length=3000)
    ownership_evidence = models.TextField(max_length=3000)
    brand_model = models.CharField(max_length=200, blank=True)
    lost_location = models.CharField(max_length=200)
    lost_date = models.DateField()
    serial_number = models.CharField(max_length=150, blank=True)
    supporting_image = models.ImageField(upload_to=upload_path, blank=True)
    status = models.CharField(
        max_length=15, choices=STATUSES, default="PENDING", db_index=True
    )
    admin_remarks = models.TextField(blank=True, max_length=2000)
    ai_analysis = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def get_absolute_url(self):
        return reverse("claim_detail", args=[self.pk])


class ClaimEvent(models.Model):
    claim = models.ForeignKey(Claim, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    status = models.CharField(max_length=15)
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
