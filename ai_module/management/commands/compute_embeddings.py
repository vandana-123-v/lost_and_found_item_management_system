import logging
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from items.models import Item, ItemImage
from ai_module.models import ImageEmbedding
from ai_module.services.clip_service import store_embedding, CLIPError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Compute and store CLIP image embeddings for approved found-item images."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Maximum number of items to process (0 = all).",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Recompute embeddings even if they already exist.",
        )

    def handle(self, *args, **options):
        from django.conf import settings

        if not getattr(settings, "CLIP_ENABLED", False):
            raise CommandError(
                "CLIP is not enabled. Set CLIP_ENABLED=True in .env first."
            )

        limit = options["limit"]
        overwrite = options["overwrite"]

        qs = Item.objects.filter(
            item_type="FOUND",
            status__in=["APPROVED", "MATCHED"],
            images__isnull=False,
        ).distinct()

        if limit > 0:
            qs = qs[:limit]

        items = list(qs)
        total_items = len(items)
        if not total_items:
            self.stdout.write("No eligible items found.")
            return

        processed = 0
        skipped = 0
        failed = 0

        for item in items:
            images = list(item.images.all())
            images_to_process = []
            for img in images:
                if not overwrite and ImageEmbedding.objects.filter(item_image=img).exists():
                    skipped += 1
                else:
                    images_to_process.append(img)

            if not images_to_process:
                processed += 1
                continue

            try:
                with transaction.atomic():
                    for img in images_to_process:
                        store_embedding(img)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  Item {item.pk} ({item.title[:40]}): "
                        f"{len(images_to_process)} embedding(s) stored."
                    )
                )
                processed += 1
            except CLIPError as exc:
                failed += 1
                self.stdout.write(
                    self.style.WARNING(f"  Item {item.pk}: {exc}")
                )
            except Exception as exc:
                failed += 1
                logger.error("CLIP backfill failed for item %s: %s", item.pk, exc)
                self.stdout.write(
                    self.style.WARNING(f"  Item {item.pk}: {exc}")
                )

        total_embeddings = ImageEmbedding.objects.count()
        summary = (
            f"\nProcessed: {processed}/{total_items} items | "
            f"Skipped: {skipped} existing | Failed: {failed}\n"
            f"Total embeddings in DB: {total_embeddings}\n"
        )
        self.stdout.write(self.style.SUCCESS(summary))
