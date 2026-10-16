from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.conf import settings
from accounts.models import User
from items.models import Item, Category
from items.forms import CategoryForm
from items.services import filtered_items, moderate_item
from claims.models import Claim
from claims.forms import DecisionForm
from claims.services import decide_claim
from notifications.services import notify
from ai_module.models import MatchSuggestion
from ai_module.services.matching import analyze_report
from core.models import AuditLog, ContactMessage
from core.services import staff_required, audit
from .services import statistics, chart_data
from .forms import SendNotificationForm


@login_required
def dashboard(request):
    if request.user.is_staff:
        return redirect("admin_dashboard")
    stats = statistics(request.user)
    stats.pop("Pending reports")
    stats["Unread notifications"] = request.user.notifications.filter(
        is_read=False
    ).count()
    return render(
        request,
        "user/dashboard.html",
        {
            "title": "Your dashboard",
            "stats": stats,
            "recent_items": request.user.items.select_related("category")[:5],
            "recent_claims": request.user.claims.select_related("item")[:5],
            "activity": AuditLog.objects.filter(user=request.user).exclude(
                action__startswith="Admin"
            )[:6],
            "matches": active_matches(request.user)[:3],
        },
    )


def active_matches(user):
    qs = (
        MatchSuggestion.objects.select_related("source_item", "matched_item")
        .prefetch_related("source_item__images", "matched_item__images")
        .filter(
            source_item__status__in=["APPROVED", "MATCHED"],
            matched_item__status__in=["APPROVED", "MATCHED"],
        )
    )
    return (
        qs
        if user.is_staff
        else qs.filter(Q(source_item__user=user) | Q(matched_item__user=user))
    )


@login_required
def matches(request):
    return render(
        request,
        "user/matches.html",
        {
            "title": "Suggested matches",
            "ai_configured": settings.AI_ENABLED and bool(settings.GEMINI_API_KEY),
            "page_obj": Paginator(active_matches(request.user), 12).get_page(
                request.GET.get("page")
            ),
        },
    )


@staff_required
def admin_dashboard(request):
    stats = statistics()
    stats.update(
        {
            "Total users": User.objects.count(),
            "Active users": User.objects.filter(is_active=True).count(),
            "Pending claims": Claim.objects.filter(
                status__in=["PENDING", "UNDER_REVIEW"]
            ).count(),
            "Approved claims": Claim.objects.filter(status="APPROVED").count(),
        }
    )
    return render(
        request,
        "admin_panel/dashboard.html",
        {
            "title": "Administration overview",
            "stats": stats,
            "charts": chart_data(),
            "pending_items": Item.objects.filter(status="PENDING")[:5],
            "pending_claims": Claim.objects.filter(
                status__in=["PENDING", "UNDER_REVIEW"]
            ).select_related("item")[:5],
        },
    )


@staff_required
def users(request):
    qs = User.objects.all().order_by("-date_joined")
    query = request.GET.get("q", "")[:200]
    if query:
        qs = qs.filter(
            Q(username__icontains=query)
            | Q(email__icontains=query)
            | Q(full_name__icontains=query)
        )
    if request.GET.get("active") in ["yes", "no"]:
        qs = qs.filter(is_active=request.GET["active"] == "yes")
    return render(
        request,
        "admin_panel/users.html",
        {
            "title": "Manage users",
            "page_obj": Paginator(qs, 20).get_page(request.GET.get("page")),
        },
    )


@staff_required
def user_detail(request, pk):
    member = get_object_or_404(User, pk=pk)
    return render(
        request,
        "admin_panel/user_detail.html",
        {
            "title": str(member),
            "member": member,
            "user_items": member.items.all()[:30],
            "user_claims": member.claims.select_related("item")[:30],
        },
    )


@staff_required
@require_POST
def user_action(request, pk):
    with transaction.atomic():
        member = get_object_or_404(User.objects.select_for_update(), pk=pk)
        if member.pk == request.user.pk or member.is_superuser or member.is_staff:
            messages.error(
                request, "Staff accounts cannot be deactivated from this screen."
            )
        else:
            member.is_active = not member.is_active
            member.save(update_fields=["is_active"])
            audit(
                request.user,
                "Admin account activated"
                if member.is_active
                else "Admin account blocked",
                member,
            )
            messages.success(request, "Account status updated.")
    return redirect("admin_user_detail", pk=pk)


@staff_required
def admin_items(request):
    qs = filtered_items(
        Item.objects.select_related("user", "category").prefetch_related("images"),
        request.GET,
    )
    return render(
        request,
        "admin_panel/items.html",
        {
            "title": "Manage reports",
            "page_obj": Paginator(qs, 15).get_page(request.GET.get("page")),
            "categories": Category.objects.all(),
            "statuses": Item.STATUSES,
        },
    )


@staff_required
@require_POST
def item_action(request, pk):
    get_object_or_404(Item, pk=pk)
    try:
        item = moderate_item(
            pk,
            request.user,
            request.POST.get("status"),
            request.POST.get("remarks", "")[:2000],
        )
        if item.status in ["APPROVED", "MATCHED"]:
            if not analyze_report(item):
                messages.info(
                    request, "Report updated. AI matching is temporarily unavailable."
                )
        messages.success(request, "Report status updated.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("item_detail", pk=pk)


@staff_required
def admin_claims(request):
    qs = Claim.objects.select_related("item", "claimant")
    if request.GET.get("status"):
        qs = qs.filter(status=request.GET["status"])
    if request.GET.get("q"):
        qs = qs.filter(
            Q(item__title__icontains=request.GET["q"][:200])
            | Q(claimant__username__icontains=request.GET["q"][:200])
        )
    return render(
        request,
        "claims/list.html",
        {
            "title": "Review claims",
            "admin_mode": True,
            "page_obj": Paginator(qs, 15).get_page(request.GET.get("page")),
            "statuses": Claim.STATUSES,
        },
    )


@staff_required
@require_POST
def claim_action(request, pk):
    get_object_or_404(Claim, pk=pk)
    form = DecisionForm(request.POST)
    if form.is_valid():
        try:
            decide_claim(
                pk,
                request.user,
                form.cleaned_data["status"],
                form.cleaned_data["remarks"],
            )
            messages.success(request, "Decision recorded and claimant notified.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    else:
        messages.error(request, "Choose a valid status and provide remarks.")
    return redirect("claim_detail", pk=pk)


@staff_required
def categories(request, pk=None):
    category = get_object_or_404(Category, pk=pk) if pk else None
    form = CategoryForm(request.POST or None, instance=category)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        audit(request.user, "Admin category saved", saved)
        return redirect("admin_categories")
    return render(
        request,
        "admin_panel/categories.html",
        {"title": "Categories", "form": form, "categories": Category.objects.all()},
    )


@staff_required
@require_POST
def delete_category(request, pk):
    category = get_object_or_404(Category, pk=pk)
    try:
        with transaction.atomic():
            audit(request.user, "Admin category deleted", category, category.name)
            category.delete()
        messages.success(request, "Category deleted.")
    except ProtectedError:
        messages.error(request, "This category has reports. Deactivate it instead.")
    return redirect("admin_categories")


@staff_required
def admin_notifications(request):
    form = SendNotificationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        note = notify(
            form.cleaned_data["recipient"],
            form.cleaned_data["title"],
            form.cleaned_data["message"],
            important=True,
        )
        audit(request.user, "Admin notification sent", note)
        messages.success(request, "Notification sent.")
        return redirect("admin_notifications")
    return render(
        request,
        "admin_panel/notifications.html",
        {
            "title": "Send a notification",
            "form": form,
            "contacts": ContactMessage.objects.order_by("-created_at")[:30],
        },
    )


@staff_required
def audit_logs(request):
    qs = AuditLog.objects.select_related("user")
    if request.GET.get("q"):
        qs = qs.filter(
            Q(action__icontains=request.GET["q"][:200])
            | Q(description__icontains=request.GET["q"][:200])
        )
    return render(
        request,
        "admin_panel/audit.html",
        {
            "title": "Audit trail",
            "page_obj": Paginator(qs, 25).get_page(request.GET.get("page")),
        },
    )


@staff_required
def system_settings(request):
    return render(
        request,
        "admin_panel/settings.html",
        {
            "title": "System settings",
            "ai_enabled": settings.AI_ENABLED and bool(settings.GEMINI_API_KEY),
            "email_enabled": bool(settings.EMAIL_HOST),
            "model_name": settings.GEMINI_MODEL,
            "database_engine": settings.DATABASES["default"]["ENGINE"].split(".")[-1],
        },
    )
