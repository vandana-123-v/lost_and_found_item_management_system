"""Test the exact multimodal JSON API used by image matching, without private data."""

import base64
import io
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from dotenv import dotenv_values
from PIL import Image, ImageDraw
from ai_module.services.gemini_service import (
    AIUnavailable,
    ERROR_HELP,
    FEATURE_SCHEMA,
    MATCH_SCHEMA,
    available_models,
    generate,
    validate_configuration,
)


class Command(BaseCommand):
    help = "Check Gemini configuration and a small synthetic image request, or list generateContent models. Never prints keys or private images."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument(
            "--list-models",
            action="store_true",
            help="List accessible generateContent models instead of making a generation request.",
        )

    def handle(self, *args, **options):
        self.stdout.write(f"Model: {settings.GEMINI_MODEL}")
        self.stdout.write(
            f"AI enabled: {settings.AI_ENABLED}; API key present: {bool(settings.GEMINI_API_KEY.strip())}"
        )
        env = dotenv_values(settings.BASE_DIR / ".env")
        if (
            env.get("GEMINI_API_KEY")
            and env["GEMINI_API_KEY"] != settings.GEMINI_API_KEY
        ):
            self.stdout.write(
                self.style.WARNING(
                    "A process/system environment variable overrides GEMINI_API_KEY from .env. Check the terminal environment and restart Django."
                )
            )
        try:
            validate_configuration()
            if options["list_models"]:
                for name in available_models():
                    self.stdout.write(
                        name
                        + (" (configured)" if name == settings.GEMINI_MODEL else "")
                    )
                self.stdout.write(
                    "This list shows generateContent support, not image/JSON compatibility. Set an image-capable model in .env, then run check_ai without flags."
                )
                return
            self.stdout.write(
                "Sending two small generated object drawings to test image input and structured JSON. This uses API quota; no stored reports or user photos are sent."
            )
            image = Image.new("RGB", (128, 128), "white")
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((30, 25, 95, 112), radius=15, fill="blue")
            stream = io.BytesIO()
            image.save(stream, "PNG")
            part = {
                "inlineData": {
                    "mimeType": "image/png",
                    "data": base64.b64encode(stream.getvalue()).decode(),
                }
            }
            self.stdout.write(
                "Step 1/2: testing photo feature extraction and its JSON schema..."
            )
            generate(
                "Describe this blue object drawing using the supplied JSON schema.",
                {"categories": ["Bags", "Other"]},
                FEATURE_SCHEMA,
                extra_parts=[part],
            )
            self.stdout.write("Step 2/2: testing multi-image comparison...")
            generate(
                "Compare these two object drawings. Give visual similarity score 0-100 and a short reason.",
                {},
                MATCH_SCHEMA,
                extra_parts=[{"text": "Image A"}, part, {"text": "Image B"}, part],
            )
            self.stdout.write(
                self.style.SUCCESS(
                    "PASS: Gemini accepted the key, model, image input and JSON schema, and returned a valid result. Retry Search by image in the application."
                )
            )
        except AIUnavailable as exc:
            code = exc.code if exc.code in ERROR_HELP else "UNAVAILABLE"
            raise CommandError(f"[{code}] {ERROR_HELP[code]}") from None
