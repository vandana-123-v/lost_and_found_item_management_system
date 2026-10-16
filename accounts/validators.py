import re
from django.core.exceptions import ValidationError


class StrongPasswordValidator:
    def validate(self, password, user=None):
        if not all(
            re.search(pattern, password)
            for pattern in [r"[A-Z]", r"[a-z]", r"[0-9]", r"[^A-Za-z0-9\s]"]
        ):
            raise ValidationError(self.get_help_text(), code="weak_password")

    def get_help_text(self):
        return "Use uppercase, lowercase, a number, and a special character."
