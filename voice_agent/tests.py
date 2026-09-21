from pathlib import Path
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings

from .models import Call, KnowledgeItem
from .services import (
    format_exotel_callerid,
    format_exotel_from,
    make_stream_url,
    resolve_gemini_voice,
    system_instructions,
)


class PageSmokeTests(TestCase):
    @override_settings(ADMIN_AUTH_ENABLED=True, ADMIN_USERNAME="", ADMIN_PASSWORD="", DEBUG=True)
    def test_debug_mode_with_missing_admin_credentials_does_not_block_local_pages(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Vardha Voice Connect")

    @override_settings(ADMIN_AUTH_ENABLED=True, ADMIN_USERNAME="", ADMIN_PASSWORD="", DEBUG=False)
    def test_non_debug_mode_without_admin_credentials_fails_closed(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 503)

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

    def test_dashboard_api_returns_real_counts(self):
        Call.objects.create(phone_number="+919876543210", status="COMPLETED")
        Call.objects.create(phone_number="+919876543211", status="FAILED")
        response = self.client.get("/api/dashboard")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_calls"], 2)
        self.assertEqual(data["completed_calls"], 1)
        self.assertEqual(data["failed_calls"], 1)


class ProviderFormattingTests(TestCase):
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

    def test_stream_url_carries_only_logical_voice_key(self):
        from django.conf import settings
        with patch.object(settings, "PUBLIC_BASE_URL", "https://example.test"), patch.object(settings, "PUBLIC_BASE_URL_IS_PLACEHOLDER", False):
            self.assertEqual(
                make_stream_url(42, "female"),
                "wss://example.test/ws/exotel/42/?v=3&sample-rate=8000&voice=female",
            )

    def test_invalid_logical_voice_is_rejected(self):
        from django.conf import settings
        with patch.object(settings, "PUBLIC_BASE_URL", "https://example.test"), patch.object(settings, "PUBLIC_BASE_URL_IS_PLACEHOLDER", False):
            with self.assertRaises(ValueError):
                make_stream_url(42, "Kore")

    def test_voice_ids_are_server_side_and_allowlisted(self):
        self.assertEqual(resolve_gemini_voice("primary"), "Kore")
        self.assertEqual(resolve_gemini_voice("female"), "Aoede")
        with self.assertRaises(ValueError):
            resolve_gemini_voice("Kore")


class CallApiTests(TestCase):
    def test_invalid_call_number_is_rejected_without_provider_call(self):
        with patch("voice_agent.views.start_exotel_call") as start_mock:
            response = self.client.post(
                "/api/call",
                data='{"phone_number":"123"}',
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("valid mobile number", response.json()["error"])
        start_mock.assert_not_called()

    def test_arbitrary_voice_id_is_rejected(self):
        response = self.client.post(
            "/api/call",
            data='{"phone_number":"+919876543210","voice":"Kore"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid voice selection", response.json()["error"])

    @patch("voice_agent.views.start_exotel_call")
    @patch("voice_agent.views.settings.GEMINI_API_KEY", "test-gemini-key")
    def test_selected_logical_voice_reaches_provider_service(self, start_mock):
        def fake_start(call, voice_key="primary"):
            call.exotel_sid = "test-sid"
            call.status = "QUEUED"
            call.save(update_fields=["exotel_sid", "status"])
            return {"call": {"sid": "test-sid"}}

        start_mock.side_effect = fake_start
        response = self.client.post(
            "/api/call",
            data='{"phone_number":"+919876543210","voice":"female"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["voice"], "female")
        self.assertEqual(start_mock.call_args.kwargs["voice_key"], "female")

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
        self.assertIn("voice=primary", sent_payload["StreamUrl"])

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


class CallHistoryDeleteTests(TestCase):
    def setUp(self):
        self.selected = Call.objects.create(phone_number="+919876543210", status="COMPLETED")
        self.other = Call.objects.create(phone_number="+919876543211", status="FAILED")

    def test_delete_removes_only_selected_record(self):
        response = self.client.delete(f"/api/call/{self.selected.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Call.objects.filter(id=self.selected.id).count(), 0)
        self.assertEqual(Call.objects.filter(id=self.other.id).count(), 1)

    def test_delete_missing_call_returns_404(self):
        response = self.client.delete("/api/call/999999")
        self.assertEqual(response.status_code, 404)

    def test_call_detail_rejects_unsupported_methods(self):
        response = self.client.put(f"/api/call/{self.selected.id}", data="{}", content_type="application/json")
        self.assertEqual(response.status_code, 405)

    def test_history_template_contains_delete_action(self):
        response = self.client.get("/history")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "deleteCall")
        self.assertContains(response, "Delete")


class WebhookAndFrontendRegressionTests(TestCase):
    def test_passthru_missing_sid_is_safe(self):
        response = self.client.get("/webhooks/exotel/passthru")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

    def test_csrf_bootstrap(self):
        response = self.client.get("/api/csrf")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get("csrfToken"))
        self.assertIn("csrftoken", response.cookies)

    def test_service_worker_cache_version(self):
        response = self.client.get("/service-worker.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("APP_VERSION", response.content.decode())
        self.assertIn("1.4.4", response.content.decode())
        self.assertIn("caches.open", response.content.decode())
        self.assertIn("event.respondWith", response.content.decode())
        self.assertIn("/api/", response.content.decode())


    def test_runtime_uses_version_file_not_stale_env_version(self):
        from django.conf import settings
        self.assertEqual(settings.APP_VERSION, (Path(__file__).resolve().parent.parent / "VERSION.txt").read_text(encoding="utf-8").strip())

    def test_main_pages_reference_current_versioned_assets(self):
        from django.conf import settings
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn(f"styles.css?v={settings.APP_VERSION}", body)
        self.assertIn(f"app.js?v={settings.APP_VERSION}", body)
        self.assertNotIn("v=1.4.1", body)

    def test_frontend_contains_voice_selection_and_delete(self):
        base = Path(__file__).parent
        js = (base / "static/voice_agent/app.js").read_text()
        html = (base / "templates/voice_agent/base_page.html").read_text()
        self.assertIn('value="primary"', html)
        self.assertIn('value="female"', html)
        self.assertIn('deleteCall', js)
        self.assertIn("method:'DELETE'", js)
        self.assertIn('delete-action', js)


class AudioProtocolRegressionTests(TestCase):
    def test_consumer_uses_negotiated_exotel_audio_format(self):
        source = Path(__file__).with_name("consumers.py").read_text()
        self.assertIn("media_format", source)
        self.assertIn("self._exotel_sample_rate", source)
        self.assertIn("audioop.ulaw2lin", source)
        self.assertIn("audioop.lin2ulaw", source)

    def test_realtime_session_requests_audio_output(self):
        source = Path(__file__).with_name("consumers.py").read_text()
        self.assertIn('"responseModalities": ["AUDIO"]', source)
        self.assertIn('"generationConfig"', source)
        self.assertIn('self.gemini_voice', source)
        self.assertNotIn('"temperature": 0.4', source)

    def test_exotel_outbound_media_uses_streamSid_protocol_key(self):
        source = Path(__file__).with_name("consumers.py").read_text()
        self.assertIn('"streamSid": self.stream_sid', source)
        self.assertIn('"sequenceNumber": str(self._outbound_seq)', source)
        self.assertNotIn('"stream_sid": self.stream_sid,\n            "media"', source)

    def test_telephony_stream_defaults_to_8khz(self):
        from django.conf import settings
        self.assertEqual(settings.EXOTEL_STREAM_SAMPLE_RATE, 8000)


class GeminiLiveRegressionTests(TestCase):
    def test_system_instructions_is_called_off_async_orm_context(self):
        source = Path(__file__).with_name("consumers.py").read_text()
        self.assertIn("await sync_to_async(system_instructions, thread_sensitive=True)()", source)
        self.assertIn("_flush_pending_input", source)
        self.assertIn("_watch_greeting_audio", source)
        self.assertIn("parse_qs", source)
        self.assertNotIn('"systemInstruction": {"parts": [{"text": system_instructions()}]}', source)

    def test_hindi_first_system_policy_and_kb_guardrail(self):
        instructions = system_instructions()
        self.assertIn("Default to natural, everyday Indian Hindi", instructions)
        self.assertIn("natural Hinglish", instructions)
        self.assertIn("do not invent or guess prices", instructions)
        self.assertIn("single source of truth", instructions)

    def test_public_auth_is_present_and_internal_summary_errors_are_not_returned_to_users(self):
        settings_source = Path(__file__).resolve().parent.parent / "config" / "settings.py"
        middleware_source = Path(__file__).with_name("middleware.py").read_text()
        services_source = Path(__file__).with_name("services.py").read_text()
        self.assertIn("ADMIN_AUTH_ENABLED", settings_source.resolve().read_text())
        self.assertIn("AdminBasicAuthMiddleware", middleware_source)
        self.assertIn("Summary generation was unavailable; transcript retained.", services_source)
        self.assertNotIn("Provider detail: {exc}", services_source)

    def test_ai_failure_is_preserved_when_exotel_reports_completed(self):
        call = Call.objects.create(
            phone_number="+918127942905",
            exotel_sid="test-sid",
            error_message="Gemini Live connection failed: test",
            status="IN_PROGRESS",
        )
        response = self.client.post(
            "/webhooks/exotel/status",
            data={"CallSid": "test-sid", "Status": "completed"},
        )
        self.assertEqual(response.status_code, 200)
        call.refresh_from_db()
        self.assertEqual(call.status, "FAILED")


class ServiceWorkerCacheRegressionTests(TestCase):
    def test_service_worker_is_versioned_network_first_and_api_safe(self):
        response = self.client.get('/service-worker.js')
        self.assertEqual(response.status_code, 200)
        body = response.content.decode('utf-8')
        self.assertIn("const APP_VERSION =", body)
        self.assertIn("1.4.4", body)
        self.assertIn("caches.open", body)
        self.assertIn("event.respondWith", body)
        self.assertIn("/api/", body)
        self.assertIn("no-store", response.headers.get("Cache-Control", ""))

    def test_offline_fallback_is_documented_in_frontend(self):
        source = (Path(__file__).parent / "static/voice_agent/app.js").read_text()
        self.assertIn("navigator.onLine === false", source)
        self.assertIn("Browser is offline", source)
