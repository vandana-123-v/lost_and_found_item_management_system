from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from .models import Notification


@login_required
def inbox(request):
    return render(
        request,
        "notifications/list.html",
        {
            "title": "Notifications",
            "page_obj": Paginator(request.user.notifications.all(), 20).get_page(
                request.GET.get("page")
            ),
        },
    )


@login_required
@require_POST
def mark_read(request, pk=None):
    qs = Notification.objects.filter(user=request.user)
    if pk:
        get_object_or_404(qs, pk=pk)
        qs = qs.filter(pk=pk)
    qs.update(is_read=True)
    if request.headers.get("Accept") == "application/json":
        return JsonResponse(
            {
                "ok": True,
                "unread": request.user.notifications.filter(is_read=False).count(),
            }
        )
    return redirect("notifications")
