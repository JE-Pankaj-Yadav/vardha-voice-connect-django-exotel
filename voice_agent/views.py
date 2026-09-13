import json
import os
import logging
from datetime import datetime

import requests

from django.conf import settings
from django.db import transaction, connection
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie

from .models import Call, KnowledgeItem
from .services import normalize_exotel_status, start_exotel_call, refresh_call_from_exotel

log = logging.getLogger(__name__)


def page_context(active):
    return {"active": active, "app_name": settings.APP_NAME, "app_version": settings.APP_VERSION}


def service_worker(request):
    """Serve the navigation service worker from the site root so it can cover /call, /knowledge, etc."""
    js = """const CACHE = 'vvc-v1-1';
const APP_ROUTES = ['/', '/call', '/knowledge', '/history'];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE)
      .then(cache => cache.addAll(APP_ROUTES))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(key => key !== CACHE).map(key => caches.delete(key))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET' || new URL(request.url).origin !== self.location.origin) return;
  // Never cache API responses: health, CSRF and call/KB/history data must be live.
  if (new URL(request.url).pathname.startsWith('/api/')) return;

  // Navigation: prefer the live Django page, but fall back to the cached page
  // when Chrome/Android is temporarily offline (including DevTools Offline).
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then(response => {
          const copy = response.clone();
          caches.open(CACHE).then(cache => cache.put(request, copy));
          return response;
        })
        .catch(() => caches.match(request).then(cached => cached || caches.match('/')) )
    );
    return;
  }

  event.respondWith(
    caches.match(request).then(cached => {
      if (cached) return cached;
      return fetch(request).then(response => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then(cache => cache.put(request, copy));
        }
        return response;
      });
    })
  );
});
"""
    return HttpResponse(js, content_type="application/javascript; charset=utf-8", headers={"Cache-Control": "no-cache"})


def chrome_devtools_config(request):
    # Chrome DevTools probes this path automatically. It is not an app error.
    return HttpResponse(status=204)


def dashboard(request):
    return render(request, "voice_agent/base_page.html", {**page_context("dashboard"), "page": "dashboard"})


def make_call_page(request):
    return render(request, "voice_agent/base_page.html", {**page_context("call"), "page": "call"})


def knowledge_page(request):
    return render(request, "voice_agent/base_page.html", {**page_context("knowledge"), "page": "knowledge"})


def history_page(request):
    return render(request, "voice_agent/base_page.html", {**page_context("history"), "page": "history"})


def call_detail(request, call_id):
    return render(request, "voice_agent/base_page.html", {**page_context("history"), "page": "detail", "call_id": call_id})


@ensure_csrf_cookie
def api_csrf(request):
    """Return a fresh CSRF token and ensure the csrftoken cookie is issued."""
    return JsonResponse({"ok": True, "csrfToken": get_token(request)})


def api_health(request):
    missing_exotel = []
    if not settings.EXOTEL_ACCOUNT_SID:
        missing_exotel.append("EXOTEL_ACCOUNT_SID")
    if not settings.EXOTEL_API_KEY:
        missing_exotel.append("EXOTEL_API_KEY")
    if not settings.EXOTEL_API_TOKEN:
        missing_exotel.append("EXOTEL_API_TOKEN")
    if not settings.EXOTEL_CALLER_ID:
        missing_exotel.append("EXOTEL_CALLER_ID")
    sid = str(settings.EXOTEL_ACCOUNT_SID or "")
    expected_base = settings.EXOTEL_EXPECTED_API_BASE if sid else ""
    domain_warning = ""
    if getattr(settings, "EXOTEL_API_BASE_WAS_OVERRIDDEN", False):
        domain_warning = (
            "An old EXOTEL_API_BASE value was found in .env and was ignored because "
            f"Account SID '{sid}' requires {expected_base}. The app now uses {expected_base}."
        )
    public_base = settings.PUBLIC_BASE_URL
    public_wss_ready = bool(public_base and not getattr(settings, "PUBLIC_BASE_URL_IS_PLACEHOLDER", True))
    database_ready = True
    database_engine = connection.settings_dict.get("ENGINE", "")
    try:
        connection.ensure_connection()
    except Exception as exc:
        database_ready = False
        log.warning("Database health check failed: %s", exc)
    public_wss_message = (
        "Public WSS is ready."
        if public_wss_ready
        else "Public WSS is not configured. Exotel cannot connect to localhost; set PUBLIC_BASE_URL to a real HTTPS tunnel URL."
    )
    ai_provider = getattr(settings, "AI_PROVIDER", "gemini")
    ai_key_configured = bool(settings.GEMINI_API_KEY) if ai_provider == "gemini" else bool(settings.OPENAI_API_KEY)
    ready = (not missing_exotel) and ai_key_configured and public_wss_ready
    return JsonResponse({
        "ok": True,
        "ready": ready and database_ready,
        "database_ready": database_ready,
        "database_engine": database_engine,
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "django": True,
        "exotel_configured": not missing_exotel,
        "exotel_missing": missing_exotel,
        "exotel_api_base": settings.EXOTEL_API_BASE,
        "exotel_expected_api_base": expected_base if sid else "",
        "exotel_domain_warning": domain_warning,
        "exotel_account_sid_configured": bool(sid),
        "exotel_account_sid_preview": ("*" * max(0, len(sid) - 4) + sid[-4:]) if sid else "",
        "ai_provider": ai_provider,
        "ai_configured": ai_key_configured,
        "gemini_configured": bool(settings.GEMINI_API_KEY),
        "gemini_live_model": settings.GEMINI_LIVE_MODEL,
        "openai_configured": bool(settings.OPENAI_API_KEY),
        "public_base_url": public_base,
        "public_wss_ready": public_wss_ready,
        "public_wss_message": public_wss_message,
        "public_wss_source": "PUBLIC_BASE_URL" if os.getenv("PUBLIC_BASE_URL", "").strip() else ("RENDER_EXTERNAL_HOSTNAME" if os.getenv("RENDER_EXTERNAL_HOSTNAME") else "not configured"),
        "agentstream_account_enablement": "requires Exotel account/feature validation",
        "trial_note": "Exotel trial outbound API may require verified account users or KYC approval.",
        "stream_endpoint": public_wss_ready,
    })


def api_make_call(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    phone = str(body.get("phone_number", "")).strip()
    if not phone.startswith("+") or len(phone) < 10 or len(phone) > 16:
        return JsonResponse({"error": "Enter a valid mobile number in international format, e.g. +919876543210."}, status=400)
    ai_provider = getattr(settings, "AI_PROVIDER", "gemini")
    if ai_provider == "gemini" and not settings.GEMINI_API_KEY:
        return JsonResponse({"error": "GEMINI_API_KEY is missing. Add it to Render Environment or .env and restart."}, status=400)
    if ai_provider != "gemini" and not settings.OPENAI_API_KEY:
        return JsonResponse({"error": "OPENAI_API_KEY is missing for the selected AI provider."}, status=400)
    with transaction.atomic():
        call = Call.objects.create(phone_number=phone)
        try:
            data = start_exotel_call(call)
        except Exception as exc:
            call.status = "FAILED"
            call.error_message = str(exc)[:4000]
            call.save(update_fields=["status", "error_message"])
            log.exception("Exotel call failed")
            message = str(exc)
            # Configuration mistakes are client/setup errors, not upstream gateway failures.
            status = 400 if (
                message.startswith("Exotel configuration is incomplete.")
                or message.startswith("PUBLIC_BASE_URL")
                or message.startswith("EXOTEL_ACCOUNT_SID")
                or message.startswith("Exotel HTTP 400:")
                or message.startswith("Exotel accepted the API credentials but rejected the destination number")
                or message.startswith("Exotel rejected the outbound call because this trial account is not KYC compliant")
                or message.startswith("Exotel authentication failed")
                or message.startswith("Exotel rejected the destination in the 'From' field")
                or message.startswith("PUBLIC_BASE_URL")
            ) else 502
            return JsonResponse({"error": message, "call_id": call.id}, status=status)
    return JsonResponse({"ok": True, "call_id": call.id, "sid": call.exotel_sid, "status": call.status, "provider": "Exotel", "provider_response": data})


def api_knowledge(request):
    if request.method == "GET":
        rows = KnowledgeItem.objects.all().values("id", "title", "content", "active", "updated_at")
        return JsonResponse({"items": list(rows)}, safe=False)
    if request.method == "POST":
        try:
            body = json.loads(request.body or "{}")
            title, content = str(body.get("title", "")).strip(), str(body.get("content", "")).strip()
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        if not title or not content:
            return JsonResponse({"error": "Title and content are required."}, status=400)
        item = KnowledgeItem.objects.create(title=title[:180], content=content)
        return JsonResponse({"ok": True, "item": {"id": item.id, "title": item.title, "content": item.content, "active": item.active}})
    return JsonResponse({"error": "Method not allowed"}, status=405)


def api_knowledge_item(request, item_id):
    item = get_object_or_404(KnowledgeItem, id=item_id)
    if request.method == "PUT":
        try:
            body = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        item.title = str(body.get("title", item.title)).strip()[:180]
        item.content = str(body.get("content", item.content)).strip()
        active_value = body.get("active", item.active)
        if isinstance(active_value, str):
            active_value = active_value.strip().lower() not in {"false", "0", "no", "off", ""}
        item.active = bool(active_value)
        item.save()
        return JsonResponse({"ok": True})
    if request.method == "DELETE":
        item.delete()
        return JsonResponse({"ok": True})
    return JsonResponse({"error": "Method not allowed"}, status=405)



@csrf_exempt
def exotel_passthru(request):
    """Capture stream/recording metadata sent by Exotel Passthru."""
    payload = request.GET.dict()
    payload.update(request.POST.dict())
    if not payload and request.body:
        try:
            body_payload = json.loads(request.body or "{}")
            if isinstance(body_payload, dict):
                payload.update({str(k): v for k, v in body_payload.items()})
        except Exception:
            pass
    stream_raw = payload.get("Stream")
    if stream_raw:
        try:
            nested = json.loads(stream_raw)
            if isinstance(nested, dict):
                payload.update({f"Stream[{k}]": val for k, val in nested.items()})
        except Exception:
            pass

    sid = payload.get("CallSid") or payload.get("call_sid") or payload.get("Sid") or payload.get("sid")
    if not sid:
        return JsonResponse({"ok": True, "ignored": "missing sid"})

    try:
        call = Call.objects.get(exotel_sid=str(sid))
    except Call.DoesNotExist:
        return JsonResponse({"ok": True, "ignored": "unknown sid"})

    status_raw = payload.get("Stream[Status]") or payload.get("Status") or payload.get("status")
    mapped = normalize_exotel_status(status_raw)
    recording = (
        payload.get("Stream[RecordingUrl]")
        or payload.get("RecordingUrl")
        or payload.get("recording_url")
        or payload.get("RecordingURL")
    )
    duration = payload.get("Stream[Duration]") or payload.get("Duration") or payload.get("duration")
    stream_error = payload.get("Stream[Error]") or payload.get("Error") or payload.get("error")
    detailed = payload.get("Stream[DetailedStatus]") or payload.get("DetailedStatus")

    changed = False
    if mapped:
        call.status = mapped
        changed = True
        if mapped == "ANSWERED" and not call.answered_at:
            call.answered_at = timezone.now()
        if mapped in {"COMPLETED", "FAILED", "BUSY", "NO_ANSWER", "CANCELED"}:
            call.ended_at = timezone.now()
    if recording:
        call.recording_url = str(recording)[:500]
        changed = True
    if duration:
        try:
            call.duration_seconds = max(0, int(float(duration)))
            changed = True
        except (TypeError, ValueError):
            pass
    if stream_error or detailed:
        call.error_message = " | ".join(x for x in [str(detailed or "").strip(), str(stream_error or "").strip()] if x)[:4000]
        changed = True
    if changed:
        call.save()

    return JsonResponse({"ok": True})

def api_history(request):
    rows = []
    calls = list(Call.objects.all()[:100])
    # Reconcile only a few recent active calls. This keeps the history page
    # current without making the page wait on dozens of provider requests.
    now = timezone.now()
    active = {"QUEUED", "RINGING", "ANSWERED", "IN_PROGRESS"}
    refreshed = 0
    for c in calls:
        if refreshed >= 5:
            break
        if c.status in active and c.exotel_sid and c.created_at and (now - c.created_at).total_seconds() < 1800:
            refresh_call_from_exotel(c)
            refreshed += 1
    calls = list(Call.objects.all()[:100])
    for c in calls:
        rows.append({
            "id": c.id, "phone_number": c.phone_number, "sid": c.exotel_sid,
            "status": c.status, "duration_seconds": c.duration_seconds,
            "recording_url": (f"/api/call/{c.id}/recording" if c.recording_url else ""), "provider_recording_url": c.recording_url, "transcript": c.transcript,
            "summary": c.summary, "error_message": c.error_message,
            "created_at": c.created_at.isoformat(),
        })
    return JsonResponse({"calls": rows})



def api_call_recording(request, call_id):
    """Proxy an Exotel recording so the browser does not need Exotel credentials."""
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405)
    call = get_object_or_404(Call, id=call_id)
    if not call.exotel_sid:
        return JsonResponse({"error": "Recording is not available because the call has no Exotel SID yet."}, status=404)
    if not call.recording_url:
        refresh_call_from_exotel(call)
    if not call.recording_url:
        return JsonResponse({"error": "Recording is not available yet. Exotel may still be preparing it."}, status=404)
    try:
        upstream = requests.get(call.recording_url, auth=(settings.EXOTEL_API_KEY, settings.EXOTEL_API_TOKEN), stream=True, timeout=30)
        if not upstream.ok:
            return JsonResponse({"error": f"Exotel recording returned HTTP {upstream.status_code}."}, status=502)
        content_type = upstream.headers.get("content-type", "audio/mpeg")
        response = StreamingHttpResponse(upstream.iter_content(chunk_size=64 * 1024), content_type=content_type)
        response["Content-Disposition"] = "inline"
        if upstream.headers.get("content-length"):
            response["Content-Length"] = upstream.headers["content-length"]
        return response
    except requests.RequestException as exc:
        log.exception("Recording proxy failed")
        return JsonResponse({"error": f"Recording could not be loaded: {exc}"}, status=502)

def api_call_detail(request, call_id):
    c = get_object_or_404(Call, id=call_id)
    if c.exotel_sid:
        refresh_call_from_exotel(c)
    return JsonResponse({
        "id": c.id, "phone_number": c.phone_number, "sid": c.exotel_sid,
        "status": c.status, "duration_seconds": c.duration_seconds,
        "recording_url": (f"/api/call/{c.id}/recording" if c.recording_url else ""), "provider_recording_url": c.recording_url, "transcript": c.transcript,
        "summary": c.summary, "discussed": c.discussed, "questions": c.questions,
        "requirements": c.requirements, "important_points": c.important_points,
        "error_message": c.error_message, "created_at": c.created_at.isoformat(),
    })


@csrf_exempt
def exotel_status_callback(request):
    payload = request.POST.dict()
    if not payload:
        try:
            payload = json.loads(request.body or "{}")
        except Exception:
            payload = {}
    sid = payload.get("CallSid") or payload.get("call_sid") or payload.get("Sid") or payload.get("sid")
    status_raw = payload.get("Status") or payload.get("status") or payload.get("CallStatus")
    if not sid:
        return JsonResponse({"ok": True, "ignored": "missing sid"})
    try:
        call = Call.objects.get(exotel_sid=str(sid))
    except Call.DoesNotExist:
        return JsonResponse({"ok": True, "ignored": "unknown sid"})
    mapped = normalize_exotel_status(status_raw)
    if mapped:
        call.status = mapped
        if mapped == "ANSWERED":
            call.answered_at = timezone.now()
        if mapped in {"COMPLETED", "FAILED", "BUSY", "NO_ANSWER", "CANCELED"}:
            call.ended_at = timezone.now()
        for key in ("RecordingUrl", "recording_url", "RecordingURL"):
            if payload.get(key):
                call.recording_url = payload[key]
                break
        duration = payload.get("DialCallDuration") or payload.get("duration") or payload.get("Duration")
        if duration:
            try:
                call.duration_seconds = int(float(duration))
            except ValueError:
                pass
        call.save()
    return JsonResponse({"ok": True})
