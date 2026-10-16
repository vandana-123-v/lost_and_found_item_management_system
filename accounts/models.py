from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from core.uploads import upload_path


class User(AbstractUser):
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150)
    phone = models.CharField(
        max_length=20,
        validators=[
            RegexValidator(r"^\+?[0-9 ()-]{7,20}$", "Enter a valid phone number.")
        ],
    )
    avatar = models.ImageField(upload_to=upload_path, blank=True)

    def save(self, *args, **kwargs):
        self.email = self.email.lower().strip()
        self.username = self.username.lower().strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.full_name or self.username


class LoginAttempt(models.Model):
    key = models.CharField(max_length=64, unique=True)
    failures = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField()
