from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from accounts.models import User
from items.models import Category, Item
from claims.forms import ClaimForm
from claims.models import Claim
from claims.services import submit_claim, decide_claim


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], AI_ENABLED=False
)
class MySQLConcurrencyTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor != "mysql":
            self.skipTest("Row-lock concurrency requires MySQL.")
        self.finder = User.objects.create_user("finder", "finder@demo.test", "Pass!234")
        self.user = User.objects.create_user(
            "claimant", "claimant@demo.test", "Pass!234"
        )
        self.other = User.objects.create_user("other", "other@demo.test", "Pass!234")
        self.admin = User.objects.create_user(
            "reviewer", "reviewer@demo.test", "Pass!234", is_staff=True
        )
        category = Category.objects.create(name="Concurrency category")
        self.item = Item.objects.create(
            user=self.finder,
            item_type="FOUND",
            title="Test item",
            description="Test",
            category=category,
            primary_color="Blue",
            event_date=timezone.localdate(),
            location="Library",
            status="APPROVED",
        )

    def form(self):
        form = ClaimForm(
            {
                "description": "Blue bag",
                "ownership_evidence": "Hidden patch in the internal pocket",
                "lost_location": "Library",
                "lost_date": str(timezone.localdate()),
            }
        )
        assert form.is_valid(), form.errors
        return form

    def test_simultaneous_duplicate_claim_is_prevented(self):
        gate = Barrier(2)

        def worker():
            close_old_connections()
            try:
                form = self.form()
                gate.wait(timeout=10)
                try:
                    submit_claim(form, self.item.pk, self.user)
                    return "created"
                except ValidationError:
                    return "rejected"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: worker(), range(2)))
        self.assertCountEqual(results, ["created", "rejected"])
        self.assertEqual(Claim.objects.count(), 1)

    def test_competing_approvals_assign_exactly_one_owner(self):
        claims = [
            submit_claim(self.form(), self.item.pk, user)
            for user in [self.user, self.other]
        ]
        gate = Barrier(2)

        def worker(pk):
            close_old_connections()
            try:
                gate.wait(timeout=10)
                try:
                    decide_claim(
                        pk, self.admin, "APPROVED", "Evidence checked in person"
                    )
                    return "approved"
                except ValidationError:
                    return "rejected"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, [claim.pk for claim in claims]))
        self.assertCountEqual(results, ["approved", "rejected"])
        self.assertEqual(Claim.objects.filter(status="APPROVED").count(), 1)
