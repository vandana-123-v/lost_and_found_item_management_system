from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from .models import AuditLog


def audit(user, action, obj=None, description="", request=None):
    return AuditLog.objects.create(
        user=user if user and user.is_authenticated else None,
        action=action,
        entity_type=obj.__class__.__name__ if obj else "",
        entity_id=str(obj.pk) if obj else "",
        description=description,
        ip_address=request.META.get("REMOTE_ADDR") if request else None,
    )


def staff_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_active or not request.user.is_staff:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped
