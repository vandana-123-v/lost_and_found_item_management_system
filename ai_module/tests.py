import io
import tempfile
from unittest.mock import patch, Mock
import torch
import numpy as np
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from items.models import Item, ItemImage, Category
from .services.image_search import search_by_image
from .services.gemini_service import AIUnavailable


def photo():
    data = io.BytesIO()
    Image.new("RGB", (50, 50), "blue").save(data, "PNG")
    return SimpleUploadedFile("bag.png", data.getvalue(), content_type="image/png")


FEATURES = {
    "object": "Backpack",
    "category": "Bags",
    "primary_color": "Blue",
    "features": ["Two pockets"],
    "description": "Blue backpack",
}


@override_settings(
    AI_ENABLED=True,
    CLIP_ENABLED=False,
    GEMINI_API_KEY="test-only",
    SECURE_SSL_REDIRECT=False,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class ImageSearchTests(TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        override = override_settings(MEDIA_ROOT=folder.name)
        override.enable()
        self.addCleanup(override.disable)
        self.member = User.objects.create_user(
            "searcher", "searcher@example.test", "Password!23"
        )
        self.finder = User.objects.create_user(
            "finder", "finder@example.test", "Password!23"
        )
        self.category, _ = Category.objects.get_or_create(name="Bags")
        self.item = self.make_item()
        self.client.force_login(self.member)

    def make_item(self, **kwargs):
        values = dict(
            user=self.finder,
            title="Found backpack",
            description="Blue backpack",
            item_type="FOUND",
            status="APPROVED",
            category=self.category,
            primary_color="Blue",
            location="Library",
            event_date=timezone.localdate(),
            private_identifying_details="SECRET mark",
        )
        values.update(kwargs)
        item = Item.objects.create(**values)
        ItemImage.objects.create(item=item, image=photo())
        return item

    def result(self, score=90, pk=None):
        return {
            "matches": [
                {
                    "item_id": pk or self.item.pk,
                    "score": score,
                    "reason": "Same shape and color.",
                }
            ]
        }

    def test_login_required_and_link_from_matches(self):
        self.assertContains(
            self.client.get(reverse("matches")), reverse("image_search")
        )
        self.client.logout()
        self.assertEqual(self.client.get(reverse("image_search")).status_code, 302)

    @override_settings(AI_ENABLED=False)
    @patch("ai_module.services.image_search.generate")
    def test_configuration_notice_and_no_provider_calls(self, generate):
        response = self.client.post(
            reverse("image_search"), {"image": photo(), "consent": "on"}
        )
        self.assertContains(response, "not configured")
        generate.assert_not_called()

    @patch("ai_module.services.image_search.generate")
    def test_upload_to_results_and_claim_link(self, generate):
        generate.side_effect = [FEATURES, self.result()]
        response = self.client.post(
            reverse("image_search"), {"image": photo(), "consent": "on"}
        )
        self.assertContains(response, "90%")
        self.assertContains(response, reverse("claim_create", args=[self.item.pk]))
        self.assertEqual(Item.objects.count(), 1)
        self.assertEqual(ItemImage.objects.count(), 1)
        payload = str(generate.call_args)
        self.assertNotIn("SECRET mark", payload)
        parts = generate.call_args.kwargs["extra_parts"]
        self.assertEqual(sum("inlineData" in part for part in parts), 2)

    @patch("ai_module.services.image_search.generate")
    def test_only_available_found_images_are_compared(self, generate):
        for override in [
            {"status": "PENDING"},
            {"status": "RETURNED"},
            {"status": "CLAIMED"},
            {"item_type": "LOST"},
            {"user": self.member},
        ]:
            self.make_item(**override)
        generate.side_effect = [FEATURES, self.result()]
        result = search_by_image(self.member, photo())
        self.assertEqual(result["eligible"], 1)
        self.assertEqual(result["compared"], 1)

    @patch("ai_module.services.image_search.generate")
    def test_no_candidates_avoids_api(self, generate):
        result = search_by_image(self.member, photo(), location="Elsewhere")
        self.assertEqual(result["eligible"], 0)
        generate.assert_not_called()

    @patch("ai_module.services.image_search.generate")
    def test_hallucinated_ids_and_duplicates_rejected(self, generate):
        for value in [
            self.result(pk=999999),
            {"matches": []},
            {"matches": self.result()["matches"] * 2},
        ]:
            generate.side_effect = [FEATURES, value]
            with self.assertRaises(AIUnavailable):
                search_by_image(self.member, photo())

    @patch("ai_module.services.image_search.generate")
    def test_low_scores_are_not_shown_as_matches(self, generate):
        generate.side_effect = [FEATURES, self.result(30)]
        result = search_by_image(self.member, photo())
        self.assertEqual(result["results"], [])

    @patch("ai_module.services.image_search.generate")
    def test_returned_during_search_is_not_shown(self, generate):
        def compare(*args, **kwargs):
            if generate.call_count == 1:
                return FEATURES
            Item.objects.filter(pk=self.item.pk).update(status="RETURNED")
            return self.result()

        generate.side_effect = compare
        self.assertEqual(search_by_image(self.member, photo())["results"], [])

    @patch(
        "ai_module.services.image_search.generate", side_effect=AIUnavailable("quota")
    )
    def test_provider_failure_has_friendly_message(self, generate):
        response = self.client.post(
            reverse("image_search"), {"image": photo(), "consent": "on"}
        )
        self.assertContains(response, "AI matching could not finish")
        self.assertEqual(Item.objects.count(), 1)

    @patch("ai_module.services.image_search.generate")
    def test_consent_and_real_image_required(self, generate):
        for data in [
            {"image": photo()},
            {"image": SimpleUploadedFile("bad.png", b"not an image"), "consent": "on"},
        ]:
            response = self.client.post(reverse("image_search"), data)
            self.assertEqual(response.status_code, 200)
        generate.assert_not_called()

    @patch("ai_module.services.image_search.generate")
    def test_search_limit(self, generate):
        generate.side_effect = [FEATURES, self.result()] * 5
        for _ in range(5):
            self.client.post(
                reverse("image_search"), {"image": photo(), "consent": "on"}
            )
        response = self.client.post(
            reverse("image_search"), {"image": photo(), "consent": "on"}
        )
        self.assertContains(response, "reached five image searches")
        self.assertEqual(generate.call_count, 10)


@override_settings(
    CLIP_ENABLED=True,
    CLIP_MODEL="ViT-B/32",
    CLIP_THRESHOLD=50,
    AI_ENABLED=False,
    GEMINI_API_KEY="",
    SECURE_SSL_REDIRECT=False,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class ClipImageSearchTests(TestCase):
    """Tests for the CLIP-based image search path."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        override = override_settings(MEDIA_ROOT=folder.name)
        override.enable()
        self.addCleanup(override.disable)
        self.member = User.objects.create_user(
            "searcher", "searcher@example.test", "Password!23"
        )
        self.finder = User.objects.create_user(
            "finder", "finder@example.test", "Password!23"
        )
        self.category, _ = Category.objects.get_or_create(name="Bags")
        self.item = self.make_item()
        self.client.force_login(self.member)

    def make_item(self, **kwargs):
        values = dict(
            user=self.finder,
            title="Found backpack",
            description="Blue backpack",
            item_type="FOUND",
            status="APPROVED",
            category=self.category,
            primary_color="Blue",
            location="Library",
            event_date=timezone.localdate(),
            private_identifying_details="SECRET mark",
        )
        values.update(kwargs)
        item = Item.objects.create(**values)
        ItemImage.objects.create(item=item, image=photo())
        return item

    @patch("ai_module.views.clip_image_search")
    def test_clip_view_uses_clip_service(self, mock_clip_search):
        """When CLIP_ENABLED, the view calls clip_image_search instead of Gemini."""
        mock_clip_search.return_value = {
            "results": [], "compared": 0, "eligible": 0, "features": None,
        }
        response = self.client.post(
            reverse("image_search"), {"image": photo(), "consent": "on"}
        )
        self.assertEqual(response.status_code, 200)
        mock_clip_search.assert_called_once()

    @patch("ai_module.views.clip_image_search")
    def test_clip_view_shows_enabled_notice(self, mock_clip_search):
        """The CLIP-enabled notice is shown when CLIP_ENABLED is True."""
        mock_clip_search.return_value = {
            "results": [], "compared": 0, "eligible": 0, "features": None,
        }
        response = self.client.post(
            reverse("image_search"), {"image": photo(), "consent": "on"}
        )
        self.assertContains(response, "Local CLIP image matching is enabled")

    @patch("ai_module.views.clip_image_search")
    def test_clip_consent_label_changes(self, mock_clip_search):
        """Consent label shows generic text when CLIP is enabled."""
        mock_clip_search.return_value = {
            "results": [], "compared": 0, "eligible": 0, "features": None,
        }
        response = self.client.post(
            reverse("image_search"), {"image": photo(), "consent": "on"}
        )
        self.assertContains(response, "Consent for this search")
        self.assertNotContains(response, "Send this image to Google Gemini")

    @patch("ai_module.services.clip_service.clip_image_search")
    def test_clip_search_no_candidates_empty(self, mock_search):
        """CLIP search with no eligible items returns empty results."""
        mock_search.return_value = {
            "results": [], "compared": 0, "eligible": 0, "features": None,
        }
        from ai_module.services.clip_service import clip_image_search
        result = clip_image_search(self.member, photo())
        self.assertEqual(result["eligible"], 0)
        self.assertEqual(result["results"], [])

    def test_clip_model_is_cached(self):
        """_get_model uses lru_cache for singleton loading."""
        from ai_module.services.clip_service import _get_model
        _get_model.cache_clear()
        with patch("ai_module.services.clip_service.open_clip") as mock_oc:
            mock_model = Mock()
            mock_preprocess = Mock()
            mock_oc.create_model_and_transforms.return_value = (
                mock_model, Mock(), mock_preprocess
            )
            m1, _ = _get_model()
            m2, _ = _get_model()
            self.assertIs(m1, m2)
        _get_model.cache_clear()

    @patch("ai_module.services.clip_service._get_model")
    def test_clip_similarity_mapping(self, mock_get_model):
        """Cosine similarity maps correctly to 0-100 score."""
        from ai_module.services.clip_service import similarity_to_score

        self.assertEqual(similarity_to_score(1.0), 100)
        self.assertEqual(similarity_to_score(0.0), 50)
        self.assertEqual(similarity_to_score(-1.0), 0)
        self.assertEqual(similarity_to_score(0.5), 75)
        self.assertEqual(similarity_to_score(-0.5), 25)

    @patch("ai_module.services.clip_service._get_model")
    def test_clip_compute_embedding_returns_normalized_vector(self, mock_get_model):
        """compute_embedding returns a L2-normalized float32 array."""
        mock_model = Mock()
        mock_preprocess = lambda x: torch.randn(3, 224, 224)
        mock_model.encode_image = Mock(
            return_value=torch.tensor([[0.3, 0.4, 0.0, 0.0] + [0.0] * 508], dtype=torch.float32)
        )
        mock_model.eval = Mock()
        mock_get_model.return_value = (mock_model, mock_preprocess)

        img_io = io.BytesIO()
        Image.new("RGB", (64, 64), color="blue").save(img_io, format="PNG")
        img_io.seek(0)

        from ai_module.services.clip_service import compute_embedding
        result = compute_embedding(img_io)
        self.assertEqual(result.dtype, np.float32)
        self.assertAlmostEqual(np.linalg.norm(result), 1.0, places=4)

    @patch("ai_module.services.clip_service._get_model")
    def test_clip_store_embedding_persists(self, mock_get_model):
        """store_embedding creates an ImageEmbedding record with correct data."""
        import numpy as np
        from ai_module.models import ImageEmbedding
        from ai_module.services.clip_service import store_embedding

        mock_model = Mock()
        mock_preprocess = lambda x: torch.randn(3, 224, 224)
        mock_model.encode_image = Mock(
            return_value=torch.ones(1, 512, dtype=torch.float32)
        )
        mock_model.eval = Mock()
        mock_get_model.return_value = (mock_model, mock_preprocess)

        img = self.item.images.first()
        emb = store_embedding(img)

        self.assertTrue(ImageEmbedding.objects.filter(item_image=img).exists())
        vec = emb.get_vector()
        self.assertEqual(vec.shape, (512,))
        self.assertAlmostEqual(np.linalg.norm(vec), 1.0, places=4)
