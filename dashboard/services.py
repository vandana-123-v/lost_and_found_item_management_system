from datetime import timezone
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from items.models import Item
from claims.models import Claim
from ai_module.models import MatchSuggestion


def statistics(user=None, items=None, claims=None):
    items = Item.objects.all() if items is None else items
    claims = Claim.objects.all() if claims is None else claims
    matches = MatchSuggestion.objects.filter(
        source_item__status__in=["APPROVED", "MATCHED"],
        matched_item__status__in=["APPROVED", "MATCHED"],
    )
    if user:
        items = items.filter(user=user)
        claims = claims.filter(claimant=user)
        matches = matches.filter(Q(source_item__user=user) | Q(matched_item__user=user))
    return {
        "Lost reports": items.filter(item_type="LOST").count(),
        "Found reports": items.filter(item_type="FOUND").count(),
        "Pending reports": items.filter(status="PENDING").count(),
        "Active claims": claims.filter(
            status__in=["PENDING", "UNDER_REVIEW", "APPROVED"]
        ).count(),
        "Returned items": items.filter(status="RETURNED").count(),
        "Suggested matches": matches.count(),
    }


def chart_data(items=None, claims=None):
    items = Item.objects.all() if items is None else items
    claims = Claim.objects.all() if claims is None else claims
    monthly = list(
        items.annotate(month=TruncMonth("created_at", tzinfo=timezone.utc))
        .values("month", "item_type")
        .annotate(total=Count("id"))
        .order_by("month")
    )
    for row in monthly:
        row["month"] = row["month"].strftime("%b %Y")
    return {
        "monthly": monthly,
        "claims": list(
            claims.values("status").annotate(total=Count("id")).order_by("status")
        ),
        "categories": list(
            items.values("category__name")
            .annotate(total=Count("id"))
            .order_by("-total")
        ),
        "recovery": [
            {"status": "Returned", "total": items.filter(status="RETURNED").count()},
            {
                "status": "Other reports",
                "total": items.exclude(status="RETURNED").count(),
            },
        ],
    }
