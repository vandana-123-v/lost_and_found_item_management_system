import io
import json
from unittest.mock import Mock, patch
import requests
from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, override_settings
from .services.gemini_service import (
    AIUnavailable,
    MATCH_SCHEMA,
    generate,
    available_models,
)


def response(status=200, body=None):
    result = Mock()
    result.status_code = status
    result.content = json.dumps(body or {}).encode()
    result.json.return_value = body or {}
    if status >= 400:
        result.raise_for_status.side_effect = requests.HTTPError(
            "raw provider error with private content"
        )
    return result


def success(parts=None):
    return response(
        body={
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {
                        "parts": parts
                        or [{"text": '{"score": 95, "reason": "Similar objects"}'}]
                    },
                }
            ]
        }
    )


@override_settings(
    AI_ENABLED=True,
    GEMINI_API_KEY="private-test-key",
    GEMINI_MODEL="gemini-2.5-flash",
    GEMINI_TIMEOUT_SECONDS=60,
)
class GeminiDiagnosticsTests(SimpleTestCase):
    @patch("ai_module.services.gemini_service.requests.post")
    def test_http_causes_are_safe_and_distinct(self, post):
        cases = [
            (400, "API key not valid: private-test-key", "INVALID_KEY"),
            (403, "Permission denied private-test-key", "PERMISSION_DENIED"),
            (404, "model not found", "MODEL_NOT_FOUND"),
            (
                429,
                "Check your plan and billing details private-test-key",
                "QUOTA_EXCEEDED",
            ),
            (402, "credit depleted", "BILLING_REQUIRED"),
            (400, "unsupported schema", "INVALID_REQUEST"),
        ]
        for status, message, code in cases:
            with self.subTest(code=code):
                post.return_value = response(status, {"error": {"message": message}})
                with self.assertRaises(AIUnavailable) as raised:
                    generate("Compare", {}, MATCH_SCHEMA)
                self.assertEqual(raised.exception.code, code)
                self.assertNotIn("private-test-key", str(raised.exception))

    @patch("ai_module.services.gemini_service.requests.post")
    def test_network_causes_are_distinct(self, post):
        for exception, code in [
            (requests.Timeout, "TIMEOUT"),
            (requests.ConnectionError, "CONNECTION"),
            (requests.exceptions.SSLError, "TLS_ERROR"),
        ]:
            post.side_effect = exception("private-test-key")
            with self.assertRaises(AIUnavailable) as raised:
                generate("Compare", {}, MATCH_SCHEMA)
            self.assertEqual(raised.exception.code, code)
            self.assertNotIn("private-test-key", str(raised.exception))

    @override_settings(GEMINI_API_KEY="your_actual_gemini_api_key")
    @patch("ai_module.services.gemini_service.requests.post")
    def test_placeholder_rejected_without_network(self, post):
        with self.assertRaises(AIUnavailable) as raised:
            generate("Compare", {}, MATCH_SCHEMA)
        self.assertEqual(raised.exception.code, "NOT_CONFIGURED")
        post.assert_not_called()

    @patch("ai_module.services.gemini_service.requests.post")
    def test_multipart_answer_skips_thought_parts(self, post):
        post.return_value = success(
            [
                {"thought": True, "text": "Not part of the JSON"},
                {"text": '{"score": 95,'},
                {"text": '"reason": "Similar objects"}'},
            ]
        )
        self.assertEqual(generate("Compare", {}, MATCH_SCHEMA)["score"], 95)

    @patch("ai_module.services.gemini_service.requests.post")
    def test_blocked_truncated_and_invalid_responses(self, post):
        for body, code in [
            ({"promptFeedback": {"blockReason": "SAFETY"}}, "BLOCKED"),
            ({"candidates": [{"finishReason": "MAX_TOKENS"}]}, "TRUNCATED"),
            ({"candidates": [{"finishReason": "SAFETY"}]}, "BLOCKED"),
            ({"candidates": []}, "INVALID_RESPONSE"),
        ]:
            post.return_value = response(body=body)
            with self.assertRaises(AIUnavailable) as raised:
                generate("Compare", {}, MATCH_SCHEMA)
            self.assertEqual(raised.exception.code, code)

    @patch("ai_module.services.gemini_service.time.sleep")
    @patch("ai_module.services.gemini_service.requests.post")
    def test_one_transient_retry_can_recover(self, post, sleep):
        post.side_effect = [response(503), success()]
        self.assertEqual(generate("Compare", {}, MATCH_SCHEMA)["score"], 95)
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(1)

    @patch("ai_module.services.gemini_service.time.sleep")
    @patch("ai_module.services.gemini_service.requests.post")
    def test_transient_retry_is_bounded(self, post, sleep):
        post.return_value = response(503)
        with self.assertRaises(AIUnavailable) as raised:
            generate("Compare", {}, MATCH_SCHEMA)
        self.assertEqual(raised.exception.code, "PROVIDER_BUSY")
        self.assertEqual(post.call_count, 2)

    @override_settings(GEMINI_TIMEOUT_SECONDS=999)
    @patch("ai_module.services.gemini_service.requests.post")
    def test_configurable_timeout_is_capped(self, post):
        post.return_value = success()
        generate("Compare", {}, MATCH_SCHEMA)
        self.assertEqual(post.call_args.kwargs["timeout"], (5, 120))

    @patch("ai_module.services.gemini_service.requests.get")
    def test_available_models_paginates_and_filters(self, get):
        get.side_effect = [
            response(
                body={
                    "models": [
                        {
                            "name": "models/gemini-example",
                            "supportedGenerationMethods": ["generateContent"],
                        }
                    ],
                    "nextPageToken": "page-two",
                }
            ),
            response(
                body={
                    "models": [
                        {
                            "name": "models/embedding",
                            "supportedGenerationMethods": ["embedContent"],
                        }
                    ]
                }
            ),
        ]
        self.assertEqual(available_models(), ["gemini-example"])
        self.assertEqual(get.call_args.kwargs["params"]["pageToken"], "page-two")

    @patch("ai_module.services.gemini_service.requests.post")
    def test_command_tests_images_without_printing_key(self, post):
        feature_json = json.dumps(
            {
                "object": "Bag",
                "category": "Bags",
                "primary_color": "Blue",
                "features": [],
                "description": "A blue object drawing",
            }
        )
        post.side_effect = [success([{"text": feature_json}]), success()]
        output = io.StringIO()
        call_command("check_ai", stdout=output)
        self.assertIn("PASS:", output.getvalue())
        self.assertNotIn("private-test-key", output.getvalue())
        parts = post.call_args.kwargs["json"]["contents"][0]["parts"]
        self.assertEqual(sum("inlineData" in part for part in parts), 2)

    @patch("ai_module.services.gemini_service.requests.post")
    def test_command_error_is_safe_to_share(self, post):
        post.return_value = response(
            429, {"error": {"message": "private-test-key quota"}}
        )
        with self.assertRaises(CommandError) as raised:
            call_command("check_ai", stdout=io.StringIO())
        self.assertIn("QUOTA_EXCEEDED", str(raised.exception))
        self.assertNotIn("private-test-key", str(raised.exception))
