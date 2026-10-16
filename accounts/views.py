import hashlib
from datetime import timedelta
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordResetView
from django.db import transaction
from django.db.models import F
from django.shortcuts import render, redirect
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from core.services import audit
from notifications.services import notify
from .forms import RegisterForm, LoginForm, ProfileForm
from .models import User, LoginAttempt


def throttle_key(value):
    return hashlib.sha256(value.encode()).hexdigest()


def limited(key, limit=5):
    now = timezone.now()
    with transaction.atomic():
        row, _ = LoginAttempt.objects.select_for_update().get_or_create(
            key=throttle_key(key), defaults={"started_at": now}
        )
        if row.started_at < now - timedelta(minutes=15):
            row.failures = 0
            row.started_at = now
            row.save()
        return row.failures >= limit


def increment(key):
    LoginAttempt.objects.filter(key=throttle_key(key)).update(
        failures=F("failures") + 1
    )


def register(request):
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = form.save()
            notify(
                user,
                "Welcome to the Hub",
                "Your account is ready. Report an item or explore the community.",
            )
            audit(user, "Account registered", user, request=request)
        login(request, user)
        return redirect("dashboard")
    return render(
        request,
        "accounts/register.html",
        {"form": form, "title": "Create your account"},
    )


def sign_in(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        identifier = form.cleaned_data["username"].strip().lower()
        keys = ["account:" + identifier, "ip:" + request.META.get("REMOTE_ADDR", "")]
        locks = [limited(keys[0]), limited(keys[1], 30)]
        if any(locks):
            form.add_error(None, "Too many attempts. Please try again in 15 minutes.")
        else:
            user_record = (
                User.objects.filter(email__iexact=identifier).first()
                if "@" in identifier
                else None
            )
            user = authenticate(
                request,
                username=user_record.username if user_record else identifier,
                password=form.cleaned_data["password"],
            )
            if user:
                LoginAttempt.objects.filter(key=throttle_key(keys[0])).delete()
                login(request, user)
                request.session.set_expiry(
                    1209600 if form.cleaned_data["remember"] else 0
                )
                audit(user, "Login", user, request=request)
                target = request.POST.get("next", "")
                if target and url_has_allowed_host_and_scheme(
                    target, {request.get_host()}, require_https=request.is_secure()
                ):
                    return redirect(target)
                return redirect("dashboard")
            for key in keys:
                increment(key)
            form.add_error(None, "Incorrect credentials or inactive account.")
    return render(
        request,
        "accounts/login.html",
        {"form": form, "next": request.GET.get("next", ""), "title": "Welcome back"},
    )


@require_POST
def sign_out(request):
    logout(request)
    return redirect("home")


@login_required
def profile(request):
    form = ProfileForm(
        request.POST or None, request.FILES or None, instance=request.user
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        audit(request.user, "Profile updated", request.user, request=request)
        messages.success(request, "Profile updated.")
        return redirect("profile")
    return render(
        request, "accounts/profile.html", {"form": form, "title": "Your profile"}
    )


class SafePasswordResetView(PasswordResetView):
    template_name = "accounts/reset.html"
    email_template_name = "accounts/reset_email.txt"
    subject_template_name = "accounts/reset_subject.txt"

    def form_valid(self, form):
        key = "reset:" + self.request.META.get("REMOTE_ADDR", "")
        if limited(key, 5):
            return redirect("password_reset_done")
        increment(key)
        try:
            return super().form_valid(form)
        except Exception:
            # Always return the same response to avoid email/account enumeration.
            import logging

            logging.getLogger(__name__).warning("Password reset delivery failed.")
            return redirect("password_reset_done")
