from django.core.exceptions import ValidationError
from django.db import transaction
from core.services import audit
from items.models import Item
from notifications.services import notify
from .models import Claim, ClaimEvent

ACTIVE = ["PENDING", "UNDER_REVIEW", "APPROVED"]


@transaction.atomic
def submit_claim(form, item_id, user):
    item = Item.objects.select_for_update().get(pk=item_id)
    if (
        item.item_type != "FOUND"
        or item.status not in ["APPROVED", "MATCHED"]
        or item.user_id == user.pk
    ):
        raise ValidationError("This item is not available for you to claim.")
    if Claim.objects.filter(item=item, claimant=user, status__in=ACTIVE).exists():
        raise ValidationError("You already have an active claim for this item.")
    claim = form.save(commit=False)
    claim.item = item
    claim.claimant = user
    claim.save()
    ClaimEvent.objects.create(
        claim=claim,
        actor=user,
        status="PENDING",
        remarks="Claim submitted for administrator review.",
    )
    audit(user, "Claim submitted", claim)
    notify(
        user,
        "Claim submitted",
        "Your ownership evidence has been sent for review.",
        item=item,
        claim=claim,
    )
    return claim


@transaction.atomic
def decide_claim(claim_id, actor, status, remarks):
    reference = Claim.objects.only("item_id").get(pk=claim_id)
    item = Item.objects.select_for_update().get(pk=reference.item_id)
    claim = Claim.objects.select_for_update().get(pk=claim_id)
    if status == "CANCELLED":
        if actor.pk != claim.claimant_id or claim.status not in [
            "PENDING",
            "UNDER_REVIEW",
        ]:
            raise ValidationError("Only the claimant may cancel a pending claim.")
    elif not actor.is_staff or actor.pk in [claim.claimant_id, item.user_id]:
        raise ValidationError("An independent administrator must review this claim.")
    transitions = {
        "PENDING": ["UNDER_REVIEW", "APPROVED", "REJECTED", "CANCELLED"],
        "UNDER_REVIEW": ["APPROVED", "REJECTED", "CANCELLED"],
        "APPROVED": ["RETURNED"],
    }
    if status not in transitions.get(claim.status, []):
        raise ValidationError("That claim transition is not allowed.")
    if not remarks.strip():
        raise ValidationError("Please record verification remarks.")
    if status == "APPROVED":
        if (
            item.status not in ["APPROVED", "MATCHED"]
            or Claim.objects.filter(item=item, status__in=["APPROVED", "RETURNED"])
            .exclude(pk=claim.pk)
            .exists()
        ):
            raise ValidationError(
                "This item already has an approved claim or is no longer available."
            )
        item.status = "CLAIMED"
        # A single physical item can be assigned to only one claimant.
        for other in (
            Claim.objects.select_for_update()
            .filter(item=item, status__in=["PENDING", "UNDER_REVIEW"])
            .exclude(pk=claim.pk)
        ):
            other.status = "REJECTED"
            other.admin_remarks = (
                "The item has been assigned to another verified claimant."
            )
            other.save()
            ClaimEvent.objects.create(
                claim=other, actor=actor, status="REJECTED", remarks=other.admin_remarks
            )
            audit(actor, "Competing claim closed", other, other.admin_remarks)
            notify(
                other.claimant,
                "Claim status updated",
                other.admin_remarks,
                claim=other,
                important=True,
            )
    elif status == "RETURNED":
        item.status = "RETURNED"
    item.save(update_fields=["status", "updated_at"])
    claim.status = status
    claim.admin_remarks = remarks
    claim.save(update_fields=["status", "admin_remarks", "updated_at"])
    ClaimEvent.objects.create(claim=claim, actor=actor, status=status, remarks=remarks)
    audit(actor, "Claim " + status.lower(), claim, remarks)
    notify(
        claim.claimant,
        "Claim status updated",
        f"Claim #{claim.pk}: {claim.get_status_display()}. {remarks}",
        item=item,
        claim=claim,
        important=True,
    )
    if status in ["APPROVED", "RETURNED"]:
        notify(
            item.user,
            "Item handover update",
            f"{item.title}: {item.get_status_display()}. Please coordinate with the administrator.",
            item=item,
            important=True,
        )
    return claim
