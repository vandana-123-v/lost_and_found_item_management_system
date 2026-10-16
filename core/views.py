from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import render, redirect
from django.conf import settings
from items.models import Item
from accounts.views import limited, increment
from notifications.services import email_safe
from .forms import ContactForm


def home(request):
    form = ContactForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        key = "contact:" + request.META.get("REMOTE_ADDR", "")
        if limited(key, 5):
            form.add_error(
                None, "Please wait 15 minutes before sending another message."
            )
        else:
            increment(key)
            contact = form.save()
            email_safe(
                "Lost & Found contact request",
                contact.message,
                [settings.CONTACT_EMAIL],
            )
            messages.success(request, "Message received. Our team will review it.")
            return redirect("/#contact")
    return render(
        request,
        "public/home.html",
        {
            "contact_form": form,
            "lost_count": Item.objects.filter(item_type="LOST")
            .exclude(status="REJECTED")
            .count(),
            "found_count": Item.objects.filter(item_type="FOUND")
            .exclude(status="REJECTED")
            .count(),
            "returned_count": Item.objects.filter(status="RETURNED").count(),
        },
    )


@login_required
def avatar(request):
    if not request.user.avatar:
        raise Http404
    response = FileResponse(request.user.avatar.open("rb"))
    response["Cache-Control"] = "private, no-store"
    return response


def privacy(request):
    return render(request, "public/privacy.html", {"title": "Terms & privacy"})


def error_page(request, exception=None, status=500):
    if status == 500:
        # Do not query sessions/notifications while handling a database outage.
        from django.http import HttpResponse

        return HttpResponse(
            '<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            "<title>Temporarily unavailable</title><body><main><h1>We could not complete your request</h1>"
            "<p>Please try again shortly. Your previously saved records are unaffected.</p>"
            '<a href="/">Return home</a></main></body></html>',
            status=500,
        )
    return render(
        request,
        "error.html",
        {"status": status, "title": "Unable to complete this request"},
        status=status,
    )
