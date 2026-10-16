import logging
from datetime import timedelta
from django.db.models import Case, When, Value, IntegerField
from django.conf import settings
from items.models import Item
from ai_module.models import AIAnalysis, MatchSuggestion
from notifications.services import notify
from .gemini_service import (
    extract_item_features,
    generate_match_recommendations,
    analyze_claim_consistency,
)

logger = logging.getLogger(__name__)


def candidates(item):
    qs = Item.objects.filter(
        item_type="FOUND" if item.item_type == "LOST" else "LOST",
        status__in=["APPROVED", "MATCHED"],
        category=item.category,
        event_date__gte=item.event_date - timedelta(days=90),
        event_date__lte=item.event_date + timedelta(days=90),
    ).exclude(user=item.user)
    # Rank prefiltered candidates by public brand/color/location/keywords before bounded API calls.
    rank = Value(0, output_field=IntegerField())
    for field, value in [
        ("brand", item.brand),
        ("primary_color", item.primary_color),
        ("location", item.location),
        ("title", item.title.split()[0]),
    ]:
        if value:
            rank = rank + Case(
                When(**{field + "__icontains": value}, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
    return qs.annotate(candidate_rank=rank).order_by("-candidate_rank", "-created_at")[
        :5
    ]


def analyze_report(item, match=True):
    from .clip_service import compute_image_embedding

    clip_ok = False
    try:
        clip_ok = compute_image_embedding(item)
    except Exception:
        logger.warning("CLIP embedding skipped for item %s.", item.pk)

    try:
        result = extract_item_features(item)
        AIAnalysis.objects.create(
            item=item,
            analysis_type="FEATURES",
            result=result,
            model_used=settings.GEMINI_MODEL,
        )
        if match and item.status in ["APPROVED", "MATCHED"]:
            for other, comparison in generate_match_recommendations(item):
                if comparison["score"] < 60:
                    continue
                lost, found = (
                    (item, other) if item.item_type == "LOST" else (other, item)
                )
                suggestion, created = MatchSuggestion.objects.update_or_create(
                    source_item=lost,
                    matched_item=found,
                    defaults={
                        "score": comparison["score"],
                        "reason": comparison["reason"],
                    },
                )
                if created:
                    for user in [lost.user, found.user]:
                        notify(
                            user,
                            "Potential match discovered",
                            "A new AI suggested match is available. Similarity is not proof of ownership.",
                            item=found,
                        )
        return True
    except Exception:
        # No provider error text is persisted: it may include payloads or credentials.
        logger.warning("Report AI analysis unavailable; report retained.")
        AIAnalysis.objects.create(
            item=item,
            analysis_type="UNAVAILABLE",
            result={"message": "AI temporarily unavailable"},
            model_used=settings.GEMINI_MODEL,
        )
        return False


def analyze_claim(claim):
    try:
        claim.ai_analysis = analyze_claim_consistency(claim)
    except Exception:
        claim.ai_analysis = {
            "consistency": "UNKNOWN",
            "risk_level": "UNKNOWN",
            "observations": ["AI unavailable. Manual review is required."],
        }
    claim.save(update_fields=["ai_analysis"])
