from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from core.services import audit
from .models import Item, ItemImage, Category
from .forms import ItemForm
from .services import visible_items, filtered_items, save_report
from ai_module.services.matching import analyze_report
from ai_module.models import ImageEmbedding


@login_required
def item_list(request, mine=False):
    qs = visible_items(request.user)
    if mine:
        qs = qs.filter(user=request.user)
    else:
        qs = qs.filter(status__in=["APPROVED", "MATCHED", "CLAIMED", "RETURNED"])
        if not request.GET.get("status"):
            qs = qs.filter(status__in=["APPROVED", "MATCHED"])
    page = Paginator(filtered_items(qs, request.GET), 12).get_page(
        request.GET.get("page")
    )
    return render(
        request,
        "items/list.html",
        {
            "page_obj": page,
            "categories": Category.objects.filter(active=True),
            "statuses": Item.STATUSES,
            "title": "My reports" if mine else "Find an item",
            "mine": mine,
        },
    )


@login_required
def item_detail(request, pk):
    item = get_object_or_404(visible_items(request.user), pk=pk)
    private = request.user.is_staff or item.user_id == request.user.pk
    return render(
        request,
        "items/detail.html",
        {
            "item": item,
            "title": item.title,
            "private": private,
            "can_edit": item.user_id == request.user.pk and item.editable,
            "can_claim": item.item_type == "FOUND"
            and item.status in ["APPROVED", "MATCHED"]
            and item.user_id != request.user.pk,
            "analysis": item.analyses.filter(analysis_type="FEATURES").first()
            if private
            else None,
        },
    )


@login_required
def report(request, item_type="LOST", pk=None):
    if item_type not in ["LOST", "FOUND"]:
        raise PermissionDenied
    item = get_object_or_404(Item, pk=pk, user=request.user) if pk else None
    if item and not item.editable:
        raise PermissionDenied
    form = ItemForm(request.POST or None, request.FILES or None, instance=item)
    if request.method == "POST" and form.is_valid():
        try:
            saved = save_report(
                form, request.user, item.item_type if item else item_type, item
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            available = analyze_report(saved, match=False)
            messages.success(
                request,
                "Your report was submitted successfully."
                if available
                else "Your report was submitted successfully. AI matching is temporarily unavailable.",
            )
            return redirect(saved)
    return render(
        request,
        "items/form.html",
        {
            "form": form,
            "item": item,
            "title": "Edit report"
            if item
            else "Report a " + item_type.lower() + " item",
        },
    )


@login_required
@require_POST
def close_item(request, pk):
    with transaction.atomic():
        item = get_object_or_404(
            Item.objects.select_for_update(), pk=pk, user=request.user
        )
        if not item.editable:
            raise PermissionDenied
        item.status = "CLOSED"
        item.save(update_fields=["status", "updated_at"])
        audit(request.user, "Report closed", item)
    messages.success(request, "Report closed.")
    return redirect("my_items")


@login_required
def item_image(request, pk):
    image = get_object_or_404(ItemImage, pk=pk)
    get_object_or_404(visible_items(request.user), pk=image.item_id)
    response = FileResponse(
        image.image.open("rb"),
        content_type={
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
        }[image.image.name.rsplit(".", 1)[-1]],
    )
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
@require_POST
def remove_image(request, pk):
    picture = get_object_or_404(ItemImage, pk=pk, item__user=request.user)
    with transaction.atomic():
        item = Item.objects.select_for_update().get(pk=picture.item_id)
        if not item.editable:
            raise PermissionDenied
        picture.delete()
        item.status = "PENDING"
        item.save(update_fields=["status", "updated_at"])
        item.analyses.all().delete()
        item.lost_matches.all().delete()
        item.found_matches.all().delete()
        ImageEmbedding.objects.filter(item_image__item=item).delete()
        audit(request.user, "Report image removed", item)
    return redirect("item_edit", pk=item.pk)
