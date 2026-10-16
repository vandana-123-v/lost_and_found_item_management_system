import io
import json
import tempfile
from datetime import timedelta
from unittest.mock import patch, Mock
from PIL import Image
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from accounts.models import User
from accounts.forms import RegisterForm
from items.models import Item, Category
from items.forms import ItemForm
from items.services import moderate_item
from claims.models import Claim
from claims.forms import ClaimForm
from claims.services import submit_claim, decide_claim
from notifications.models import Notification
from notifications.services import notify
from ai_module.models import AIAnalysis, MatchSuggestion
from ai_module.services import gemini_service as gemini
from ai_module.services.matching import analyze_report, analyze_claim
from core.models import AuditLog, ContactMessage
from reports.views import safe_cell

PASSWORD = "Meadow!River482"


def picture(name="photo.png"):
    stream = io.BytesIO()
    Image.new("RGB", (32, 32), "#168c98").save(stream, "PNG")
    return SimpleUploadedFile(name, stream.getvalue(), content_type="image/png")


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    AI_ENABLED=False,
    SECURE_SSL_REDIRECT=False,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class HubTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            "finder",
            "finder@example.com",
            PASSWORD,
            full_name="Morgan Finder",
            phone="+919876543210",
        )
        cls.member = User.objects.create_user(
            "member",
            "member@example.com",
            PASSWORD,
            full_name="Alex Member",
            phone="+919876543211",
        )
        cls.other = User.objects.create_user(
            "other",
            "other@example.com",
            PASSWORD,
            full_name="Other Member",
            phone="+919876543212",
        )
        cls.admin = User.objects.create_user(
            "reviewer",
            "reviewer@example.com",
            PASSWORD,
            is_staff=True,
            full_name="Independent Reviewer",
        )
        cls.category = Category.objects.get(name="Bags")
        cls.item = Item.objects.create(
            user=cls.owner,
            item_type="FOUND",
            title="Blue backpack",
            description="A blue backpack found near the library.",
            category=cls.category,
            primary_color="Blue",
            event_date=timezone.localdate(),
            location="Library",
            status="APPROVED",
            private_identifying_details="SECRET hidden violet patch",
            serial_number="PRIVATE-SERIAL-913",
            holding_location="PRIVATE-ROOM-09",
        )

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.temp.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(self.temp.cleanup)

    def signed(self, user=None):
        self.client.force_login(user or self.member)

    def report_data(self, **overrides):
        data = {
            "title": "Blue backpack",
            "description": "A familiar blue campus backpack.",
            "category": self.category.pk,
            "primary_color": "Blue",
            "event_date": str(timezone.localdate()),
            "location": "Library",
            "private_identifying_details": "Hidden violet patch",
        }
        data.update(overrides)
        return data

    def claim_data(self):
        return {
            "description": "My blue college backpack",
            "ownership_evidence": "There is a hidden violet patch inside the left pocket.",
            "lost_location": "Library",
            "lost_date": str(timezone.localdate()),
            "brand_model": "Campus",
        }

    def make_claim(self, user=None):
        form = ClaimForm(self.claim_data())
        self.assertTrue(form.is_valid(), form.errors)
        return submit_claim(form, self.item.pk, user or self.member)

    def test_registration_hashes_password_and_notifies(self):
        response = self.client.post(
            reverse("register"),
            {
                "full_name": "New Member",
                "username": "NewUser",
                "email": "NEW@example.com",
                "phone": "+919876543210",
                "password1": PASSWORD,
                "password2": PASSWORD,
                "terms": "on",
            },
        )
        self.assertRedirects(response, reverse("dashboard"))
        user = User.objects.get(username="newuser")
        self.assertEqual(user.email, "new@example.com")
        self.assertNotEqual(user.password, PASSWORD)
        self.assertTrue(user.check_password(PASSWORD))
        self.assertTrue(user.notifications.exists())
        self.assertTrue(
            AuditLog.objects.filter(user=user, action="Account registered").exists()
        )

    def test_registration_rejects_duplicate_email_username_and_weak_password(self):
        form = RegisterForm(
            {
                "full_name": "Duplicate",
                "username": "MEMBER",
                "email": "MEMBER@example.com",
                "phone": "invalid",
                "password1": "weak",
                "password2": "different",
                "terms": "",
            }
        )
        self.assertFalse(form.is_valid())
        for field in ["username", "email", "phone", "password2", "terms"]:
            self.assertIn(field, form.errors)

    def test_login_email_and_remember_me(self):
        response = self.client.post(
            reverse("login"),
            {"username": "MEMBER@example.com", "password": PASSWORD, "remember": "on"},
        )
        self.assertRedirects(response, reverse("dashboard"))
        self.assertEqual(self.client.session["_auth_user_id"], str(self.member.pk))
        self.assertEqual(self.client.session.get_expiry_age(), 1209600)

    def test_admin_login_redirect(self):
        response = self.client.post(
            reverse("login"),
            {"username": "reviewer", "password": PASSWORD},
            follow=True,
        )
        self.assertEqual(response.redirect_chain[-1][0], reverse("admin_dashboard"))

    def test_login_lockout(self):
        for _ in range(5):
            self.client.post(
                reverse("login"), {"username": "member", "password": "wrong"}
            )
        response = self.client.post(
            reverse("login"), {"username": "member", "password": PASSWORD}
        )
        self.assertContains(response, "Too many attempts")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_login(self):
        self.member.is_active = False
        self.member.save()
        response = self.client.post(
            reverse("login"), {"username": "member", "password": PASSWORD}
        )
        self.assertContains(response, "Incorrect credentials")

    def test_external_next_is_not_followed(self):
        response = self.client.post(
            reverse("login"),
            {
                "username": "member",
                "password": PASSWORD,
                "next": "https://evil.example/",
            },
        )
        self.assertEqual(response.url, reverse("dashboard"))

    def test_logout_post_only(self):
        self.signed()
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.client.post(reverse("logout"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_csrf_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.member)
        self.assertEqual(
            client.post(
                reverse("report_item", args=["LOST"]), self.report_data()
            ).status_code,
            403,
        )
        self.assertEqual(client.post(reverse("logout")).status_code, 403)

    def test_password_reset_sends_secure_link(self):
        response = self.client.post(
            reverse("password_reset"), {"email": self.member.email}
        )
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/accounts/reset/", mail.outbox[0].body)
        self.assertNotIn(PASSWORD, mail.outbox[0].body)

    def test_password_reset_token_changes_password_and_cannot_be_reused(self):
        uid = urlsafe_base64_encode(force_bytes(self.member.pk))
        token = default_token_generator.make_token(self.member)
        response = self.client.get(reverse("password_reset_confirm", args=[uid, token]))
        password = "Another!Pass553"
        response = self.client.post(
            response.url, {"new_password1": password, "new_password2": password}
        )
        self.assertRedirects(response, reverse("password_reset_complete"))
        self.member.refresh_from_db()
        self.assertTrue(self.member.check_password(password))
        self.assertFalse(default_token_generator.check_token(self.member, token))

    def test_admin_urls_forbidden_to_member(self):
        self.signed()
        for name in [
            "admin_dashboard",
            "admin_users",
            "admin_items",
            "admin_claims",
            "admin_categories",
            "reports",
            "admin_notifications",
            "audit_logs",
            "system_settings",
        ]:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)
        self.assertEqual(
            self.client.post(
                reverse("admin_item_action", args=[self.item.pk]),
                {"status": "RETURNED"},
            ).status_code,
            403,
        )

    def test_profile_update_and_duplicate_email(self):
        self.signed()
        data = {
            "full_name": "Alex Updated",
            "username": "member",
            "email": "updated@example.com",
            "phone": "+919876543215",
        }
        self.assertRedirects(
            self.client.post(reverse("profile"), data), reverse("profile")
        )
        self.member.refresh_from_db()
        self.assertEqual(self.member.full_name, "Alex Updated")
        data["email"] = self.owner.email
        self.assertContains(
            self.client.post(reverse("profile"), data), "already registered"
        )

    def test_lost_and_found_report_submission_survives_ai_failure(self):
        self.signed()
        for kind in ["LOST", "FOUND"]:
            response = self.client.post(
                reverse("report_item", args=[kind]), self.report_data(), follow=True
            )
            self.assertContains(response, "AI matching is temporarily unavailable")
        self.assertEqual(self.member.items.count(), 2)
        self.assertFalse(self.member.items.exclude(status="PENDING").exists())

    def test_future_event_rejected(self):
        form = ItemForm(
            self.report_data(event_date=str(timezone.localdate() + timedelta(days=1)))
        )
        self.assertFalse(form.is_valid())
        self.assertIn("event_date", form.errors)

    def test_multiple_images_and_image_access(self):
        self.signed(self.owner)
        data = self.report_data(images=[picture(), picture("second.png")])
        response = self.client.post(reverse("report_item", args=["FOUND"]), data)
        self.assertEqual(response.status_code, 302)
        item = self.owner.items.latest("pk")
        self.assertEqual(item.images.count(), 2)
        image = item.images.first()
        self.signed(self.member)
        self.assertEqual(
            self.client.get(reverse("item_image", args=[image.pk])).status_code, 404
        )
        self.signed(self.owner)
        response = self.client.get(reverse("item_image", args=[image.pk]))
        self.assertEqual(response.status_code, 200)
        list(response.streaming_content)

    def test_image_spoof_and_oversize_rejected(self):
        bad = SimpleUploadedFile(
            "file.png", b"<script>alert(1)</script>", content_type="image/png"
        )
        form = ItemForm(self.report_data(), {"images": [bad]})
        self.assertFalse(form.is_valid())
        oversized = SimpleUploadedFile(
            "large.png", b"x" * (5 * 1024 * 1024 + 1), content_type="image/png"
        )
        form = ItemForm(self.report_data(), {"images": [oversized]})
        self.assertFalse(form.is_valid())
        renamed = picture("file.jpg")
        self.assertFalse(ItemForm(self.report_data(), {"images": [renamed]}).is_valid())

    def test_search_and_filters(self):
        self.signed()
        for params in [
            {"q": "backpack"},
            {"type": "FOUND", "category": self.category.pk},
            {"location": "Library"},
            {"from": str(timezone.localdate()), "sort": "oldest"},
        ]:
            self.assertContains(
                self.client.get(reverse("item_list"), params), self.item.title
            )
        self.assertNotContains(
            self.client.get(reverse("item_list"), {"type": "LOST"}), self.item.title
        )
        self.assertEqual(
            self.client.get(
                reverse("item_list"), {"from": "bad", "category": "bad"}
            ).status_code,
            200,
        )

    def test_private_fields_and_pending_report_hidden(self):
        self.signed()
        response = self.client.get(self.item.get_absolute_url())
        self.assertNotContains(response, "SECRET hidden")
        self.assertNotContains(response, "PRIVATE-SERIAL")
        self.assertNotContains(response, "PRIVATE-ROOM")
        self.item.status = "PENDING"
        self.item.save()
        self.assertEqual(self.client.get(self.item.get_absolute_url()).status_code, 404)

    def test_user_cannot_edit_other_report(self):
        self.signed()
        self.assertEqual(
            self.client.post(
                reverse("item_edit", args=[self.item.pk]), self.report_data()
            ).status_code,
            404,
        )

    def test_edit_resubmits_and_logs(self):
        self.signed(self.owner)
        response = self.client.post(
            reverse("item_edit", args=[self.item.pk]),
            self.report_data(title="Updated bag"),
        )
        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "PENDING")
        self.assertEqual(self.item.title, "Updated bag")

    def test_claim_submission_duplicate_and_own_item_protection(self):
        self.signed()
        response = self.client.post(
            reverse("claim_create", args=[self.item.pk]), self.claim_data()
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Claim.objects.count(), 1)
        response = self.client.post(
            reverse("claim_create", args=[self.item.pk]), self.claim_data()
        )
        self.assertContains(response, "already have an active claim")
        self.signed(self.owner)
        self.assertEqual(
            self.client.post(
                reverse("claim_create", args=[self.item.pk]), self.claim_data()
            ).status_code,
            403,
        )

    def test_claim_privacy_and_protected_evidence(self):
        form = ClaimForm(self.claim_data(), {"supporting_image": picture()})
        self.assertTrue(form.is_valid())
        claim = submit_claim(form, self.item.pk, self.member)
        for user in [self.owner, self.other]:
            self.signed(user)
            self.assertEqual(self.client.get(claim.get_absolute_url()).status_code, 404)
            self.assertEqual(
                self.client.get(reverse("claim_evidence", args=[claim.pk])).status_code,
                403,
            )
        self.signed(self.member)
        response = self.client.get(reverse("claim_evidence", args=[claim.pk]))
        self.assertEqual(response.status_code, 200)
        list(response.streaming_content)

    def test_report_locked_while_claim_active(self):
        self.make_claim()
        self.signed(self.owner)
        self.assertEqual(
            self.client.post(
                reverse("item_edit", args=[self.item.pk]), self.report_data()
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(reverse("item_close", args=[self.item.pk])).status_code,
            403,
        )
        with self.assertRaises(ValidationError):
            moderate_item(
                self.item.pk, self.admin, "CLOSED", "Cannot close active claim"
            )

    def test_admin_approval_rejects_competing_claim_and_returns_item(self):
        winner = self.make_claim()
        loser = self.make_claim(self.other)
        decide_claim(
            winner.pk,
            self.admin,
            "UNDER_REVIEW",
            "Verify purchase receipt at the office.",
        )
        decide_claim(winner.pk, self.admin, "APPROVED", "Receipt verified in person.")
        loser.refresh_from_db()
        self.assertEqual(loser.status, "REJECTED")
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "CLAIMED")
        decide_claim(winner.pk, self.admin, "RETURNED", "Handover completed.")
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "RETURNED")
        self.assertEqual(winner.events.count(), 4)
        self.assertTrue(
            Notification.objects.filter(user=self.member, related_claim=winner).exists()
        )
        self.signed()
        self.assertNotContains(self.client.get(reverse("item_list")), self.item.title)

    def test_claim_rejection_and_cancellation(self):
        claim = self.make_claim()
        decide_claim(claim.pk, self.admin, "REJECTED", "Evidence does not match.")
        claim.refresh_from_db()
        self.assertEqual(claim.status, "REJECTED")
        replacement = self.make_claim()
        self.signed()
        self.assertRedirects(
            self.client.post(reverse("claim_cancel", args=[replacement.pk])),
            replacement.get_absolute_url(),
        )
        replacement.refresh_from_db()
        self.assertEqual(replacement.status, "CANCELLED")

    def test_no_self_approval_even_for_staff(self):
        claim = self.make_claim()
        self.member.is_staff = True
        self.owner.is_staff = True
        for actor in [self.member, self.owner, self.other]:
            with self.assertRaises(ValidationError):
                decide_claim(claim.pk, actor, "APPROVED", "Attempted self decision")

    def test_invalid_transition_rejected(self):
        claim = self.make_claim()
        with self.assertRaises(ValidationError):
            decide_claim(claim.pk, self.admin, "RETURNED", "Cannot skip approval")

    def test_admin_post_endpoints(self):
        self.signed(self.admin)
        self.item.status = "PENDING"
        self.item.save()
        response = self.client.post(
            reverse("admin_item_action", args=[self.item.pk]),
            {"status": "APPROVED", "remarks": "Verified report"},
        )
        self.assertEqual(response.status_code, 302)
        claim = self.make_claim()
        self.client.post(
            reverse("admin_claim_action", args=[claim.pk]),
            {"status": "REJECTED", "remarks": "Evidence mismatch"},
        )
        claim.refresh_from_db()
        self.assertEqual(claim.status, "REJECTED")

    def test_category_crud_and_protected_delete(self):
        self.signed(self.admin)
        self.client.post(
            reverse("admin_categories"), {"name": "Umbrellas", "active": "on"}
        )
        category = Category.objects.get(name="Umbrellas")
        self.client.post(
            reverse("admin_category_edit", args=[category.pk]), {"name": "Umbrellas"}
        )
        category.refresh_from_db()
        self.assertFalse(category.active)
        self.client.post(reverse("admin_category_delete", args=[category.pk]))
        self.assertFalse(Category.objects.filter(pk=category.pk).exists())
        self.client.post(reverse("admin_category_delete", args=[self.category.pk]))
        self.assertTrue(Category.objects.filter(pk=self.category.pk).exists())

    def test_notifications_are_scoped_and_ajax_mark_read(self):
        own = notify(self.member, "Hello", "Your notification")
        other = notify(self.other, "Secret notice", "Other user content")
        self.signed()
        self.assertNotContains(
            self.client.get(reverse("notifications")), "Other user content"
        )
        self.assertEqual(
            self.client.post(reverse("notification_read", args=[other.pk])).status_code,
            404,
        )
        response = self.client.post(
            reverse("notification_read", args=[own.pk]), HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.json()["unread"], 0)

    def test_admin_send_notification_and_block_user(self):
        self.signed(self.admin)
        self.client.post(
            reverse("admin_notifications"),
            {
                "recipient": self.member.pk,
                "title": "Office visit",
                "message": "Please bring evidence.",
            },
        )
        self.assertTrue(self.member.notifications.filter(title="Office visit").exists())
        self.client.post(reverse("admin_user_action", args=[self.member.pk]))
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_active)
        self.client.post(reverse("admin_user_action", args=[self.admin.pk]))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_report_csv_sanitization_and_filters(self):
        self.signed(self.admin)
        self.item.title = '=HYPERLINK("evil")'
        self.item.save()
        response = self.client.get(
            reverse("reports"), {"export": "csv", "category": self.category.pk}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("'=HYPERLINK", response.content.decode())
        self.assertTrue(safe_cell("  +danger").startswith("'"))
        self.assertContains(self.client.get(reverse("reports")), "Recovery rate")

    def test_all_templates_render_for_each_role(self):
        public = [
            "home",
            "login",
            "register",
            "privacy",
            "password_reset",
            "password_reset_done",
            "password_reset_complete",
        ]
        for name in public:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.signed()
        for name in [
            "dashboard",
            "item_list",
            "my_items",
            "claim_list",
            "matches",
            "notifications",
            "profile",
            "password_change",
        ]:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("report_item", args=["FOUND"])).status_code, 200
        )
        self.assertEqual(
            self.client.get(reverse("claim_create", args=[self.item.pk])).status_code,
            200,
        )
        claim = self.make_claim()
        self.assertEqual(self.client.get(claim.get_absolute_url()).status_code, 200)
        self.signed(self.admin)
        for name in [
            "admin_dashboard",
            "admin_users",
            "admin_items",
            "admin_claims",
            "admin_categories",
            "reports",
            "admin_notifications",
            "audit_logs",
            "system_settings",
        ]:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertEqual(self.client.get(claim.get_absolute_url()).status_code, 200)
        self.assertEqual(self.client.get(self.item.get_absolute_url()).status_code, 200)
        self.assertEqual(
            self.client.get(
                reverse("admin_user_detail", args=[self.member.pk])
            ).status_code,
            200,
        )

    def test_contact_form_persists(self):
        self.client.post(
            reverse("home"),
            {
                "name": "Visitor",
                "email": "visitor@example.com",
                "message": "Please help me find my notebook.",
            },
        )
        self.assertEqual(ContactMessage.objects.count(), 1)

    def test_ai_disabled_never_breaks_reports(self):
        self.assertFalse(analyze_report(self.item))
        self.assertTrue(
            AIAnalysis.objects.filter(
                item=self.item, analysis_type="UNAVAILABLE"
            ).exists()
        )

    @override_settings(AI_ENABLED=True, GEMINI_API_KEY="test-key")
    @patch("ai_module.services.gemini_service.requests.post")
    def test_gemini_validates_structured_json(self, post):
        response = Mock()
        response.content = b"{}"
        response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "score": 83,
                                        "reason": "Same public color and location.",
                                    }
                                )
                            }
                        ]
                    }
                }
            ]
        }
        post.return_value = response
        self.assertEqual(gemini.compare_items(self.item, self.item)["score"], 83)
        payload = json.dumps(post.call_args.kwargs["json"])
        self.assertNotIn("SECRET hidden", payload)
        self.assertNotIn("PRIVATE-SERIAL", payload)
        self.assertEqual(post.call_args.kwargs["timeout"], (5, 60))

    @override_settings(AI_ENABLED=True, GEMINI_API_KEY="test-key")
    @patch("ai_module.services.gemini_service.requests.post")
    def test_gemini_rejects_malformed_and_out_of_range(self, post):
        response = Mock(content=b"{}")
        post.return_value = response
        for text in [
            "not json",
            '{"score": 101, "reason": "invalid"}',
            '{"score": 5, "reason": "ok", "secret": "bad"}',
        ]:
            response.json.return_value = {
                "candidates": [{"content": {"parts": [{"text": text}]}}]
            }
            with self.assertRaises(gemini.AIUnavailable):
                gemini.compare_items(self.item, self.item)

    @override_settings(AI_ENABLED=True, GEMINI_API_KEY="test-key")
    @patch("ai_module.services.gemini_service.requests.post")
    def test_gemini_timeout(self, post):
        import requests

        post.side_effect = requests.Timeout()
        with self.assertRaises(gemini.AIUnavailable):
            gemini.compare_items(self.item, self.item)

    @patch("ai_module.services.matching.extract_item_features")
    @patch("ai_module.services.matching.generate_match_recommendations")
    def test_match_creation_is_canonical_idempotent_and_not_approval(
        self, recommendations, features
    ):
        lost = Item.objects.create(
            user=self.member,
            item_type="LOST",
            title="Lost blue bag",
            description="Blue bag",
            category=self.category,
            primary_color="Blue",
            event_date=timezone.localdate(),
            location="Library",
            status="APPROVED",
        )
        features.return_value = {
            "object": "Bag",
            "category": "Bags",
            "primary_color": "Blue",
            "features": [],
            "description": "A blue bag",
        }
        recommendations.return_value = [
            (self.item, {"score": 88, "reason": "Same public features"})
        ]
        self.assertTrue(analyze_report(lost))
        self.assertTrue(analyze_report(lost))
        self.assertEqual(MatchSuggestion.objects.count(), 1)
        match = MatchSuggestion.objects.get()
        self.assertEqual(match.source_item, lost)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "APPROVED")
        self.assertEqual(
            self.member.notifications.filter(
                title="Potential match discovered"
            ).count(),
            1,
        )

    def test_claim_ai_unknown_does_not_decide(self):
        claim = self.make_claim()
        analyze_claim(claim)
        claim.refresh_from_db()
        self.assertEqual(claim.status, "PENDING")
        self.assertEqual(claim.ai_analysis["consistency"], "UNKNOWN")

    @override_settings(EMAIL_HOST="smtp.example.com")
    @patch("notifications.services.send_mail", side_effect=OSError("offline"))
    def test_email_failure_does_not_remove_notification(self, send):
        with self.captureOnCommitCallbacks(execute=True):
            notify(self.member, "Important", "Still available in-app", important=True)
        self.assertTrue(self.member.notifications.filter(title="Important").exists())

    def test_duplicate_report_flagged_not_deleted(self):
        self.signed(self.owner)
        self.client.post(reverse("report_item", args=["FOUND"]), self.report_data())
        self.assertTrue(self.owner.items.latest("pk").duplicate_flag)
        self.assertEqual(self.owner.items.count(), 2)

    def test_search_escapes_xss(self):
        self.signed()
        self.item.title = "<script>alert(1)</script>"
        self.item.save()
        response = self.client.get(self.item.get_absolute_url())
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;")
