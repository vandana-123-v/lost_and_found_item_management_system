from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from items.services import visible_items
from ai_module.services.matching import analyze_claim
from .models import Claim
from .forms import ClaimForm, DecisionForm
from .services import submit_claim, decide_claim


@login_required
def create(request, item_id):
    item = get_object_or_404(visible_items(request.user), pk=item_id)
    if (
        item.item_type != "FOUND"
        or item.user_id == request.user.pk
        or item.status not in ["APPROVED", "MATCHED"]
    ):
        raise PermissionDenied
    form = ClaimForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            claim = submit_claim(form, item.pk, request.user)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            analyze_claim(claim)
            messages.success(
                request, "Claim submitted. An administrator will review your evidence."
            )
            return redirect(claim)
    return render(
        request,
        "claims/form.html",
        {"form": form, "item": item, "title": "Verify your ownership"},
    )


@login_required
def claim_list(request):
    claims = Claim.objects.filter(claimant=request.user).select_related("item")
    if request.GET.get("q"):
        claims = claims.filter(
            Q(item__title__icontains=request.GET["q"][:200])
            | Q(description__icontains=request.GET["q"][:200])
        )
    if request.GET.get("status"):
        claims = claims.filter(status=request.GET["status"])
    return render(
        request,
        "claims/list.html",
        {
            "page_obj": Paginator(claims, 15).get_page(request.GET.get("page")),
            "title": "My claims",
            "statuses": Claim.STATUSES,
        },
    )


@login_required
def detail(request, pk):
    qs = Claim.objects.select_related("item", "claimant", "item__user")
    if not request.user.is_staff:
        qs = qs.filter(claimant=request.user)
    claim = get_object_or_404(qs, pk=pk)
    return render(
        request,
        "claims/detail.html",
        {
            "claim": claim,
            "title": f"Claim #{claim.pk}",
            "decision_form": DecisionForm(),
            "can_cancel": claim.claimant_id == request.user.pk
            and claim.status in ["PENDING", "UNDER_REVIEW"],
        },
    )


@login_required
@require_POST
def cancel(request, pk):
    get_object_or_404(Claim, pk=pk, claimant=request.user)
    try:
        decide_claim(pk, request.user, "CANCELLED", "Cancelled by claimant.")
        messages.success(request, "Claim cancelled.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("claim_detail", pk=pk)


@login_required
def evidence(request, pk):
    claim = get_object_or_404(Claim, pk=pk)
    if not request.user.is_staff and request.user.pk != claim.claimant_id:
        raise PermissionDenied
    if not claim.supporting_image:
        from django.http import Http404

        raise Http404
    response = FileResponse(
        claim.supporting_image.open("rb"),
        as_attachment=True,
        filename="ownership-evidence"
        + "."
        + claim.supporting_image.name.rsplit(".", 1)[-1],
    )
    response["Cache-Control"] = "private, no-store"
    return response
