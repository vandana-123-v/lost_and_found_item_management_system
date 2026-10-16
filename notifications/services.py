import logging
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from .models import Notification

logger = logging.getLogger(__name__)


def email_safe(subject, message, recipients):
    if not settings.EMAIL_HOST:
        return
    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, recipients)
    except Exception:
        logger.warning("Notification email failed; in-app notification is retained.")


def notify(user, title, message, item=None, claim=None, important=False):
    note = Notification.objects.create(
        user=user,
        title=title,
        message=message,
        related_item=item,
        related_claim=claim,
        notification_type="CLAIM" if claim else "ITEM" if item else "SYSTEM",
    )
    if important:
        transaction.on_commit(lambda: email_safe(title, message, [user.email]))
    return note
