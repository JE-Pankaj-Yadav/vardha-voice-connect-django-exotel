from unittest.mock import Mock, patch

from django.test import Client, TestCase
from django.urls import reverse

from .models import KnowledgeItem
from .services import format_exotel_callerid, format_exotel_from


class PageSmokeTests(TestCase):
    def test_all_main_pages_return_200(self):
        for path in ["/", "/call", "/knowledge", "/history"]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Vardha Voice Connect")

    def test_knowledge_api_round_trip(self):
        response = self.client.get("/api/knowledge")
        self.assertEqual(response.status_code, 200)
        before = len(response.json()["items"])

        response = self.client.post(
            "/api/knowledge",
            data='{"title":"Smoke Test","content":"This is test information."}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(KnowledgeItem.objects.filter(title="Smoke Test").count(), 1)

        response = self.client.get("/api/knowledge")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["items"]), before + 1)

    def test_exotel_from_formats_indian_e164(self):
        self.assertEqual(format_exotel_from("+918127942905"), "+918127942905")
        self.assertEqual(format_exotel_from("918127942905"), "+918127942905")
        self.assertEqual(format_exotel_from("8127942905"), "+918127942905")
        self.assertEqual(format_exotel_from("+14155552671"), "+14155552671")

    def test_exotel_callerid_uses_exophone_zero_prefix(self):
        self.assertEqual(format_exotel_callerid("08047283507"), "08047283507")
        self.assertEqual(format_exotel_callerid("+918047283507"), "08047283507")
        self.assertEqual(format_exotel_callerid("918047283507"), "08047283507")
        self.assertEqual(format_exotel_callerid("8047283507"), "08047283507")

    def test_invalid_call_number_is_rejected_without_provider_call(self):
        response = self.client.post(
            "/api/call",
            data='{"phone_number":"123"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("valid mobile number", response.json()["error"])


    @patch("voice_agent.services.requests.post")
    @patch("voice_agent.views.settings.GEMINI_API_KEY", "test-gemini-key")
    @patch("voice_agent.services.settings.EXOTEL_CALLER_ID", "08047283507")
    @patch("voice_agent.services.settings.EXOTEL_API_TOKEN", "test-token")
    @patch("voice_agent.services.settings.EXOTEL_API_KEY", "test-key")
    @patch("voice_agent.services.settings.EXOTEL_ACCOUNT_SID", "student1768")
    @patch("voice_agent.services.settings.PUBLIC_BASE_URL", "https://example.test")
    def test_invalid_from_error_is_explained(self, post_mock):
        response_mock = Mock()
        response_mock.ok = False
        response_mock.status_code = 400
        response_mock.text = "<Message>Invalid Call Parameters: Invalid 'From' specified</Message>"
        post_mock.side_effect = [response_mock, response_mock]
        response = self.client.post(
            "/api/call",
            data='{"phone_number":"+919335288731"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("rejected the destination number", response.json()["error"])
        self.assertIn("verified", response.json()["error"])
        sent_files = post_mock.call_args_list[0].kwargs["files"]
        sent_payload = {key: value[1] for key, value in sent_files}
        self.assertEqual(sent_payload["From"], "+919335288731")
        self.assertEqual(sent_payload["CallerId"], "08047283507")
        self.assertEqual(sent_payload["StreamType"], "bidirectional")
        self.assertTrue(sent_payload["StreamUrl"].startswith("wss://"))

    @patch("voice_agent.services.requests.post")
    @patch("voice_agent.views.settings.GEMINI_API_KEY", "test-gemini-key")
    @patch("voice_agent.services.settings.EXOTEL_CALLER_ID", "08047283507")
    @patch("voice_agent.services.settings.EXOTEL_API_TOKEN", "test-token")
    @patch("voice_agent.services.settings.EXOTEL_API_KEY", "test-key")
    @patch("voice_agent.services.settings.EXOTEL_ACCOUNT_SID", "student1768")
    @patch("voice_agent.services.settings.PUBLIC_BASE_URL", "https://example.test")
    def test_trial_kyc_error_is_explained(self, post_mock):
        response_mock = Mock()
        response_mock.ok = False
        response_mock.status_code = 403
        response_mock.text = "<Message>Your account is not yet KYC compliant.</Message>"
        post_mock.return_value = response_mock
        response = self.client.post(
            "/api/call",
            data='{"phone_number":"+919335288731"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("not KYC compliant", response.json()["error"])

    def test_passthru_missing_sid_is_safe(self):
        response = self.client.get("/webhooks/exotel/passthru")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

    def test_csrf_bootstrap(self):
        response = self.client.get("/api/csrf")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get("csrfToken"))
        self.assertIn("csrftoken", response.cookies)


class AudioBridgeTests(TestCase):
    def test_audioop_lts_or_builtin_available(self):
        import audioop  # noqa: F401

    def test_service_worker_cache_version(self):
        response = self.client.get('/service-worker.js')
        self.assertEqual(response.status_code, 200)
        self.assertIn('vvc-v1-1', response.content.decode())


class AudioProtocolRegressionTests(TestCase):
    def test_consumer_uses_negotiated_exotel_audio_format(self):
        from pathlib import Path
        source = Path(__file__).with_name("consumers.py").read_text()
        self.assertIn("media_format", source)
        self.assertIn("self._exotel_sample_rate", source)
        self.assertIn("audioop.ulaw2lin", source)
        self.assertIn("audioop.lin2ulaw", source)

    def test_realtime_session_requests_audio_output(self):
        from pathlib import Path
        source = Path(__file__).with_name("consumers.py").read_text()
        self.assertIn('"responseModalities": ["AUDIO"]', source)

    def test_exotel_outbound_media_uses_streamSid_protocol_key(self):
        from pathlib import Path
        source = Path(__file__).with_name("consumers.py").read_text()
        self.assertIn('"streamSid": self.stream_sid', source)
        self.assertIn('"sequenceNumber": str(self._outbound_seq)', source)
        self.assertNotIn('"stream_sid": self.stream_sid,\n            "media"', source)

    def test_telephony_stream_defaults_to_8khz(self):
        from django.conf import settings
        self.assertEqual(settings.EXOTEL_STREAM_SAMPLE_RATE, 8000)

    def test_render_public_base_url_is_used_when_explicit_url_is_empty(self):
        from django.conf import settings
        with patch.object(settings, "PUBLIC_BASE_URL", "https://vardha-voice-connect.onrender.com"):
            with patch.object(settings, "PUBLIC_BASE_URL_IS_PLACEHOLDER", False):
                from .services import make_stream_url
                self.assertEqual(
                    make_stream_url(42),
                    "wss://vardha-voice-connect.onrender.com/ws/exotel/42/?v=2&sample-rate=8000",
                )
