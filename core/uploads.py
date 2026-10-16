from pathlib import Path
from uuid import uuid4
from PIL import Image, UnidentifiedImageError
from django.core.exceptions import ValidationError


def upload_path(instance, filename):
    return f"uploads/{uuid4().hex}{Path(filename).suffix.lower()}"


def validate_image(value):
    if value.size > 5 * 1024 * 1024:
        raise ValidationError("Each image must be 5 MB or smaller.")
    allowed = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}
    suffix = Path(value.name).suffix.lower()
    if suffix not in allowed:
        raise ValidationError("Upload a JPG, PNG, or WEBP image.")
    try:
        image = Image.open(value)
        if image.format != allowed[suffix] or image.width * image.height > 25_000_000:
            raise ValidationError("Invalid image format or excessive image dimensions.")
        image.verify()
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise ValidationError("This file is not a valid image.")
    finally:
        value.seek(0)
    return value
