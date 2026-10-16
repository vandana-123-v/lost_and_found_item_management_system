from difflib import SequenceMatcher
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Case, When, Value, IntegerField
from core.services import audit
from notifications.services import notify
from .models import Item, ItemImage
from ai_module.models import ImageEmbedding
from PIL import Image

PUBLIC_STATUSES = ["APPROVED", "MATCHED", "CLAIMED", "RETURNED"]
AVAILABLE_STATUSES = ["APPROVED", "MATCHED"]


def image_fingerprint(file):
    """Small average hash for review-only duplicate detection, never ownership proof."""
    try:
        file.open("rb")
        image = Image.open(file).convert("L").resize((8, 8))
        pixels = list(image.getdata())
        average = sum(pixels) / len(pixels)
        return sum((pixel >= average) << index for index, pixel in enumerate(pixels))
    finally:
        file.seek(0)


def similar_upload(item, uploads, candidates):
    if not uploads:
        return False
    hashes = [image_fingerprint(upload) for upload in uploads]
    for other in candidates[:10]:
        for picture in other.images.all()[:3]:
            try:
                fingerprint = image_fingerprint(picture.image)
                picture.image.close()
            except (OSError, ValueError):
                continue
            if any((fingerprint ^ candidate).bit_count() <= 4 for candidate in hashes):
                return True
    return False


def visible_items(user):
    qs = Item.objects.select_related("category", "user").prefetch_related("images")
    if user.is_staff:
        return qs
    return qs.filter(Q(status__in=PUBLIC_STATUSES) | Q(user=user))


def filtered_items(qs, params):
    keyword = params.get("q", "").strip()[:200]
    if keyword:
        condition = Q()
        for field in [
            "title",
            "description",
            "brand",
            "primary_color",
            "location",
            "category__name",
        ]:
            condition |= Q(**{field + "__icontains": keyword})
        qs = qs.filter(condition).annotate(
            relevance=Case(
                When(title__icontains=keyword, then=Value(3)),
                When(brand__icontains=keyword, then=Value(2)),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
    for name, field in [
        ("type", "item_type"),
        ("status", "status"),
        ("category", "category_id"),
    ]:
        value = params.get(name)
        if value and (name != "category" or value.isdigit()):
            qs = qs.filter(**{field: value})
    for field in ["location", "brand", "primary_color"]:
        if params.get(field):
            qs = qs.filter(**{field + "__icontains": params[field][:200]})
    from datetime import date

    for key, lookup in [("from", "event_date__gte"), ("to", "event_date__lte")]:
        try:
            if params.get(key):
                qs = qs.filter(**{lookup: date.fromisoformat(params[key])})
        except ValueError:
            pass
    sort = params.get("sort")
    return qs.order_by(
        "created_at"
        if sort == "oldest"
        else "-relevance"
        if sort == "relevance" and keyword
        else "-created_at",
        "-pk",
    )


@transaction.atomic
def save_report(form, user, item_type, instance=None):
    if instance:
        locked = Item.objects.select_for_update().get(pk=instance.pk)
        if locked.user_id != user.pk or not locked.editable:
            raise ValidationError(
                "This report cannot be edited while a claim is active or after closure."
            )
    item = form.save(commit=False)
    item.user = user
    item.item_type = item_type
    item.status = "PENDING"
    similar = Item.objects.filter(
        user=user,
        item_type=item_type,
        event_date=item.event_date,
        location__iexact=item.location,
    ).exclude(pk=item.pk)
    item.duplicate_flag = any(
        SequenceMatcher(None, item.title.lower(), other.title.lower()).ratio() > 0.8
        or item.description.strip().lower() == other.description.strip().lower()
        for other in similar[:20]
    )
    if not item.duplicate_flag:
        item.duplicate_flag = similar_upload(
            item, form.cleaned_data.get("images", []), similar
        )
    item.save()
    if instance:
        item.lost_matches.all().delete()
        item.found_matches.all().delete()
        item.analyses.all().delete()
        ImageEmbedding.objects.filter(item_image__item=item).delete()
    images = form.cleaned_data.get("images", [])
    if item.images.count() + len(images) > 6:
        raise ValidationError(
            "A report can contain up to six images. Remove an existing image first."
        )
    for index, image in enumerate(images):
        ItemImage.objects.create(
            item=item, image=image, is_primary=not item.images.exists() and index == 0
        )
    audit(user, "Report updated" if instance else "Report created", item)
    notify(
        user,
        "Report submitted",
        "Your report is pending administrator verification.",
        item=item,
    )
    return item


@transaction.atomic
def moderate_item(item_id, actor, status, remarks):
    item = Item.objects.select_for_update().get(pk=item_id)
    if not actor.is_staff:
        raise ValidationError("Administrator access required.")
    transitions = {
        "PENDING": ["APPROVED", "REJECTED"],
        "REJECTED": ["APPROVED", "CLOSED"],
        "APPROVED": ["MATCHED", "CLOSED", "REJECTED", "RETURNED"],
        "MATCHED": ["APPROVED", "CLOSED", "RETURNED"],
    }
    if status not in transitions.get(item.status, []):
        raise ValidationError("That status transition is not allowed.")
    if item.claims.filter(status__in=["PENDING", "UNDER_REVIEW", "APPROVED"]).exists():
        raise ValidationError(
            "Resolve active claims through the claim review screen first."
        )
    if not remarks.strip():
        raise ValidationError("Provide a reason for the decision.")
    item.status = status
    item.save(update_fields=["status", "updated_at"])
    audit(actor, "Report " + status.lower(), item, remarks)
    notify(
        item.user,
        "Report status updated",
        f"{item.title}: {item.get_status_display()}. {remarks}",
        item=item,
        important=True,
    )
    return item
