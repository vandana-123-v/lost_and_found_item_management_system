from django.core.management.base import BaseCommand
from items.models import Item
from ai_module.services.matching import analyze_report


class Command(BaseCommand):
    help = "Retry analysis for a bounded batch of approved reports."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20)

    def handle(self, *args, **options):
        for item in Item.objects.filter(status__in=["APPROVED", "MATCHED"])[
            : max(0, min(options["limit"], 100))
        ]:
            self.stdout.write(f"{item.pk}: {analyze_report(item)}")
