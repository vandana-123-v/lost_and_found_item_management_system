import logging
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from accounts.views import limited, increment
from core.services import audit
from .forms import ImageSearchForm
from .services.gemini_service import AIUnavailable, ERROR_HELP
from .services.image_search import search_by_image
from .services.clip_service import clip_image_search, CLIPError, THRESHOLD

logger = logging.getLogger(__name__)


@login_required
def image_search(request):
    clip_enabled = getattr(settings, "CLIP_ENABLED", False)
    gemini_configured = settings.AI_ENABLED and bool(settings.GEMINI_API_KEY)
    form = ImageSearchForm(request.POST or None, request.FILES or None)
    result = None
    if request.method == "POST" and form.is_valid():
        if not clip_enabled and not gemini_configured:
            form.add_error(
                None,
                "Image matching is not configured. Ask the administrator to enable "
                "CLIP (local) or set AI_ENABLED=True with a valid GEMINI_API_KEY in .env, "
                "then restart Django.",
            )
        else:
            key = f"image-search:{request.user.pk}"
            if limited(key, 5):
                form.add_error(
                    None,
                    "You have reached five image searches. Please try again in 15 minutes.",
                )
            else:
                increment(key)
                try:
                    if clip_enabled:
                        result = clip_image_search(
                            request.user,
                            form.cleaned_data["image"],
                            form.cleaned_data["category"],
                            form.cleaned_data["location"],
                        )
                    else:
                        result = search_by_image(
                            request.user,
                            form.cleaned_data["image"],
                            form.cleaned_data["category"],
                            form.cleaned_data["location"],
                        )
                    audit(
                        request.user,
                        "Image search completed",
                        description=f"Compared {result['compared']} found reports.",
                    )
                except (AIUnavailable, CLIPError) as exc:
                    code = getattr(exc, "code", None)
                    if code and code in ERROR_HELP:
                        form.add_error(
                            None,
                            f"AI matching could not finish [{code}]. {ERROR_HELP[code]}",
                        )
                    elif isinstance(exc, CLIPError):
                        form.add_error(
                            None,
                            "Local image matching could not finish. "
                            "Ask the administrator to run python manage.py check_ai.",
                        )
                    else:
                        form.add_error(
                            None,
                            f"AI matching could not finish [{code}]. {ERROR_HELP[code]}",
                        )
                    logger.warning(
                        "Image search failed [%s]; no search image persisted.", exc
                    )
    response = render(
        request,
        "user/image_search.html",
        {
            "title": "AI matches",
            "form": form,
            "ai_configured": gemini_configured,
            "clip_enabled": clip_enabled,
            "clip_model": getattr(settings, "CLIP_MODEL", "ViT-B/32"),
            "clip_threshold": THRESHOLD,
            "search_result": result,
            "searched": result is not None,
        },
    )
    response["Cache-Control"] = "private, no-store"
    return response
