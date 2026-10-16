from django.conf import settings
from django.db import models


class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    title = models.CharField(max_length=160)
    message = models.TextField()
    notification_type = models.CharField(max_length=30, default="SYSTEM")
    related_item = models.ForeignKey(
        "items.Item", null=True, blank=True, on_delete=models.SET_NULL
    )
    related_claim = models.ForeignKey(
        "claims.Claim", null=True, blank=True, on_delete=models.SET_NULL
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
