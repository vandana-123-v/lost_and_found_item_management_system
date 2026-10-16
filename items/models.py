from django.conf import settings
from django.db import models
from django.urls import reverse
from core.uploads import upload_path


class Category(models.Model):
    name = models.CharField(max_length=80, unique=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Item(models.Model):
    TYPES = [("LOST", "Lost"), ("FOUND", "Found")]
    STATUSES = [
        (s, s.replace("_", " ").title())
        for s in [
            "PENDING",
            "APPROVED",
            "MATCHED",
            "CLAIMED",
            "RETURNED",
            "REJECTED",
            "CLOSED",
        ]
    ]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="items"
    )
    item_type = models.CharField(max_length=5, choices=TYPES)
    title = models.CharField(max_length=180)
    description = models.TextField(max_length=4000)
    private_identifying_details = models.TextField(max_length=3000, blank=True)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="items"
    )
    brand = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=100, blank=True)
    primary_color = models.CharField(max_length=60)
    secondary_color = models.CharField(max_length=60, blank=True)
    serial_number = models.CharField(max_length=150, blank=True)
    event_date = models.DateField()
    event_time = models.TimeField(null=True, blank=True)
    location = models.CharField(max_length=200)
    detailed_location = models.CharField(max_length=300, blank=True)
    holding_location = models.CharField(max_length=300, blank=True)
    contact_information = models.CharField(max_length=200, blank=True)
    additional_notes = models.TextField(max_length=2000, blank=True)
    status = models.CharField(
        max_length=12, choices=STATUSES, default="PENDING", db_index=True
    )
    duplicate_flag = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["item_type", "category", "event_date"])]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("item_detail", args=[self.pk])

    @property
    def editable(self):
        return (
            self.status in ["PENDING", "APPROVED", "REJECTED"]
            and not self.claims.filter(
                status__in=["PENDING", "UNDER_REVIEW", "APPROVED"]
            ).exists()
        )


class ItemImage(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to=upload_path)
    is_primary = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)
