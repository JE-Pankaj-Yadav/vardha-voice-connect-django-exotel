import json
import logging
from datetime import timedelta
from xml.etree import ElementTree
from urllib.parse import urlencode

import requests
from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone

from .models import Call, KnowledgeItem

log = logging.getLogger(__name__)

def format_exotel_from(phone_number):
    """Normalize the destination for Exotel Connect Voice AI.

    The current Connect Voice AI API requires the `from`/destination value in
    E.164 format (for India, for example +918127942905).
    """
    value = str(phone_number or "").strip().replace(" ", "").replace("-", "")
    if value.startswith("+"):
        return value
    if value.startswith("0") and len(value) == 11 and value[1:].isdigit():
        return "+91" + value[1:]
    if value.startswith("91") and len(value) == 12 and value[2:].isdigit():
        return "+" + value
    if len(value) == 10 and value.isdigit():
        return "+91" + value
    return value


def format_exotel_callerid(caller_id):
    """Normalize an Indian ExoPhone to the Exotel API callerid format.

    Exotel's Connect API examples use the ExoPhone as 0xxxxxxxxxx. Users
    sometimes paste the same ExoPhone as +91xxxxxxxxxx in .env, so normalize
    that provider-bound value without changing the number's identity.
    """
    value = str(caller_id or "").strip().replace(" ", "").replace("-", "")
    if value.startswith("+91") and len(value) == 13 and value[3:].isdigit():
        return "0" + value[3:]
    if value.startswith("91") and len(value) == 12 and value[2:].isdigit():
        return "0" + value[2:]
    if len(value) == 10 and value.isdigit():
        return "0" + value
    return value


SYSTEM_BASE = """You are the Vardha Voice Connect AI voice assistant.
This is a short demonstration call. You are an AI voice assistant.
Speak in simple English, use short sentences, listen before answering, and sound friendly and natural.
Answer only what the person is asking. Do not repeat information unnecessarily.
If the person is busy or wants to end the call, politely end it.
If asked whether you are a real person, say: I am an AI voice assistant.
If asked why they received the call, say: This is a short Vardha Voice Connect demonstration call. I am an AI voice assistant, and this call is showing how an AI can have a conversation over the phone.
You MUST use only the active Knowledge Base below for factual business information. Never guess or invent company details, locations, services, prices, or contact information.
If an answer is not in the Knowledge Base, say exactly: I don't have that information right now, so I don't want to guess.
Do not read the whole Knowledge Base aloud. Use only relevant facts.
At the end, thank the person briefly and say goodbye.
"""


def kb_text():
    items = list(KnowledgeItem.objects.filter(active=True).order_by("title"))
    if not items:
        return "KNOWLEDGE BASE: No active information is available. Do not guess any business facts."
    blocks = [f"[{x.title}]\n{x.content}" for x in items]
    return "ACTIVE KNOWLEDGE BASE:\n\n" + "\n\n".join(blocks)


def system_instructions():
    return SYSTEM_BASE + "\n\n" + kb_text()


def exotel_url(path):
    """Build the Exotel REST URL using the canonical Accounts/Calls path."""
    normalized = path if path.startswith("/") else "/" + path
    return (
        f"{settings.EXOTEL_API_BASE}/v1/Accounts/"
        f"{settings.EXOTEL_ACCOUNT_SID}{normalized}"
    )


def exotel_auth():
    return (settings.EXOTEL_API_KEY, settings.EXOTEL_API_TOKEN)


def make_stream_url(call_id):
    """Return the public Exotel WSS endpoint for this call.

    Local development uses an explicit HTTPS tunnel URL in PUBLIC_BASE_URL.
    Render deployments can leave PUBLIC_BASE_URL empty because settings.py
    automatically builds it from RENDER_EXTERNAL_HOSTNAME.
    """
    base = str(settings.PUBLIC_BASE_URL or "").strip().rstrip("/")
    if not base:
        raise RuntimeError(
            "Public WSS is not configured. Exotel cannot connect to localhost. "
            "For local testing, set PUBLIC_BASE_URL to a real HTTPS tunnel URL. "
            "On Render, leave it empty and the app will use the Render hostname automatically."
        )
    if getattr(settings, "PUBLIC_BASE_URL_IS_PLACEHOLDER", False):
        raise RuntimeError(
            "Public WSS is not ready. Set PUBLIC_BASE_URL to a real HTTPS URL, "
            "or deploy on Render and let the app use RENDER_EXTERNAL_HOSTNAME automatically."
        )
    if not base.startswith("https://"):
        raise RuntimeError("PUBLIC_BASE_URL must start with https:// so Exotel can open a secure WSS connection.")
    ws_base = "wss://" + base[len("https://"):].rstrip("/")
    params = {"v": "3", "sample-rate": str(settings.EXOTEL_STREAM_SAMPLE_RATE)}
    return f"{ws_base}/ws/exotel/{call_id}/?{urlencode(params)}"


def exotel_missing_settings():
    missing = []
    if not settings.EXOTEL_ACCOUNT_SID:
        missing.append("EXOTEL_ACCOUNT_SID")
    if not settings.EXOTEL_API_KEY:
        missing.append("EXOTEL_API_KEY")
    if not settings.EXOTEL_API_TOKEN:
        missing.append("EXOTEL_API_TOKEN")
    if not settings.EXOTEL_CALLER_ID:
        missing.append("EXOTEL_CALLER_ID")
    return missing


def start_exotel_call(call: Call):
    missing = exotel_missing_settings()
    if missing:
        raise RuntimeError(
            "Exotel configuration is incomplete. Missing: "
            + ", ".join(missing)
            + ". Add these values to the project's .env file and restart the server."
        )
    if getattr(settings, "PUBLIC_BASE_URL_IS_PLACEHOLDER", False):
        raise RuntimeError(
            "PUBLIC_BASE_URL is not ready. Exotel must reach the AI WebSocket over public WSS. "
            "Run a public tunnel to http://127.0.0.1:8000, set its HTTPS URL in .env as PUBLIC_BASE_URL, and restart the server."
        )

    sid = str(settings.EXOTEL_ACCOUNT_SID).strip()
    if not sid:
        raise RuntimeError("EXOTEL_ACCOUNT_SID is empty. Copy the Account SID from Exotel → API Settings and restart the server.")
    if any(ch.isspace() for ch in sid) or "/" in sid:
        raise RuntimeError("EXOTEL_ACCOUNT_SID contains invalid whitespace or '/'. Copy only the Account SID value from Exotel → API Settings.")

    exotel_from = format_exotel_from(call.phone_number)
    exotel_callerid = format_exotel_callerid(settings.EXOTEL_CALLER_ID)
    stream_url = make_stream_url(call.id)

    # Exotel's current Connect Voice AI examples use multipart form-data (-F),
    # not a URL-encoded body. Keep the documented field names/casing too.
    payload = [
        ("From", exotel_from),
        ("CallerId", exotel_callerid),
        ("StreamUrl", stream_url),
        ("StreamType", settings.EXOTEL_STREAMTYPE),
        ("Record", "true" if settings.EXOTEL_RECORD else "false"),
        ("TimeLimit", str(settings.EXOTEL_TIME_LIMIT)),
        ("CustomField", f"vvc-call-{call.id}"),
        ("StatusCallback", f"{settings.PUBLIC_BASE_URL}/webhooks/exotel/status"),
        ("StatusCallbackEvents[]", "ringing"),
        ("StatusCallbackEvents[]", "answered"),
        ("StatusCallbackEvents[]", "terminal"),
    ]

    endpoint = exotel_url("/Calls/connect.json")
    log.info(
        "Calling Exotel Connect Voice AI API endpoint: %s | From: %s | CallerId: %s | StreamUrl: %s",
        endpoint, exotel_from, exotel_callerid, stream_url,
    )

    def _post_multipart(items):
        return requests.post(
            endpoint,
            files=[(key, (None, value)) for key, value in items],
            auth=exotel_auth(),
            timeout=30,
        )

    response = _post_multipart(payload)

    # Compatibility fallback for older Exotel Connect deployments. Current
    # AgentStream documentation uses E.164, so only retry after an explicit
    # provider-side Invalid From rejection. The first request was rejected, so
    # this retry cannot duplicate an accepted call.
    if (
        response.status_code == 400
        and "invalid 'from'" in response.text.lower()
        and exotel_from.startswith("+91")
    ):
        legacy_from = "0" + exotel_from[3:]
        log.warning("Retrying Exotel Connect once with legacy From format: %s", legacy_from)
        legacy_payload = [(key, legacy_from if key == "From" else value) for key, value in payload]
        response = _post_multipart(legacy_payload)
        if response.ok:
            log.info("Exotel accepted legacy From compatibility format: %s", legacy_from)
    if not response.ok:
        body = response.text[:1000]
        body_lower = body.lower()
        if response.status_code == 401:
            raise RuntimeError(
                "Exotel authentication failed (HTTP 401). Check EXOTEL_API_KEY and "
                "EXOTEL_API_TOKEN in .env, and confirm the API domain matches the account "
                f"region. Current domain: {settings.EXOTEL_API_BASE}. Exotel response: {body}"
            )
        if response.status_code == 403 and "kyc" in body_lower:
            raise RuntimeError(
                "Exotel rejected the outbound call because this trial account is not KYC compliant. "
                "Until KYC is approved, Exotel allows outbound testing only to phone numbers that are "
                "added to the Exotel account and verified. Add/verify the destination number in "
                "Exotel → Co-workers and groups, or complete KYC, then try again. "
                f"Exotel response: {body}"
            )
        if response.status_code == 400 and "invalid 'from'" in body_lower:
            raise RuntimeError(
                "Exotel rejected the destination number in the 'From' field. The application is sending the "
                "documented direct AgentStream format: the callee in E.164 (+91XXXXXXXXXX) and the "
                "ExoPhone separately as CallerId. Because basic Exotel Dashboard CALL is already working, "
                "do not change the phone-number format again. Check that the destination is verified for "
                "trial API testing and that Connect Voice AI / AgentStream is enabled for this Exotel account. "
                f"Number entered: {call.phone_number}; Exotel From sent: {exotel_from}; "
                f"CallerId sent: {exotel_callerid}. Exotel response: {body}"
            )
        raise RuntimeError(f"Exotel HTTP {response.status_code}: {body}")
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"Exotel returned HTTP {response.status_code} but not valid JSON. "
            "The .json endpoint was requested, so this indicates an unexpected provider response. "
            f"Response: {response.text[:1000]}"
        ) from exc
    obj = data.get("call") or data.get("Call") or data
    call.exotel_sid = str(
        obj.get("sid") or obj.get("Sid") or obj.get("call_sid") or obj.get("CallSid") or ""
    )
    call.status = "QUEUED"
    call.started_at = timezone.now()
    call.error_message = ""
    call.save(update_fields=["exotel_sid", "status", "started_at", "error_message"])
    return data



def _xml_value(root, *paths):
    for path in paths:
        node = root.find(path)
        if node is not None and node.text:
            return node.text.strip()
    return ""


def refresh_call_from_exotel(call: Call):
    """Reconcile final call/recording data from Exotel's Call Details API.

    Exotel documents status callbacks as near-real-time but recommends the Call
    Details API as the fallback when callbacks are missing/incomplete and for
    recordings that become available after the first callback.
    """
    if not call.exotel_sid or not settings.EXOTEL_ACCOUNT_SID or not settings.EXOTEL_API_KEY or not settings.EXOTEL_API_TOKEN:
        return call
    endpoint = exotel_url(f"/Calls/{call.exotel_sid}")
    try:
        response = requests.get(endpoint, auth=exotel_auth(), timeout=15)
        if not response.ok:
            log.warning("Exotel call-details reconciliation failed: HTTP %s", response.status_code)
            return call
        content_type = response.headers.get("content-type", "").lower()
        status = recording = duration = ""
        if "json" in content_type:
            payload = response.json()
            obj = payload.get("call", payload)
            status = obj.get("status", "")
            recording = obj.get("presignedrecordingurl") or obj.get("PreSignedRecordingUrl") or obj.get("recordingurl") or obj.get("RecordingUrl") or ""
            duration = obj.get("duration", "")
        else:
            root = ElementTree.fromstring(response.text)
            status = _xml_value(root, ".//call/status", ".//status")
            recording = _xml_value(root, ".//call/presignedrecordingurl", ".//call/PreSignedRecordingUrl", ".//call/recordingurl", ".//call/RecordingUrl")
            duration = _xml_value(root, ".//call/duration", ".//duration")
        mapped = normalize_exotel_status(status)
        update_fields = ["provider_checked_at"]
        call.provider_checked_at = timezone.now()
        if mapped:
            call.status = mapped
            update_fields.append("status")
            if mapped == "ANSWERED" and not call.answered_at:
                call.answered_at = timezone.now()
                update_fields.append("answered_at")
            if mapped in {"COMPLETED", "FAILED", "BUSY", "NO_ANSWER"} and not call.ended_at:
                call.ended_at = timezone.now()
                update_fields.append("ended_at")
        if recording:
            call.recording_url = str(recording)[:500]
            update_fields.append("recording_url")
        if duration:
            try:
                call.duration_seconds = max(0, int(float(duration)))
                update_fields.append("duration_seconds")
            except (TypeError, ValueError):
                pass
        call.save(update_fields=list(dict.fromkeys(update_fields)))
    except Exception as exc:
        log.warning("Exotel call-details reconciliation failed: %s", exc)
    return call


def recording_proxy_url(call_id):
    return f"/api/call/{call_id}/recording"

def generate_summary(call_id):
    call = Call.objects.get(id=call_id)
    if not call.transcript.strip():
        return

    provider = getattr(settings, "AI_PROVIDER", "gemini")
    if provider == "gemini":
        if not settings.GEMINI_API_KEY:
            call.summary = "Summary unavailable because GEMINI_API_KEY is not configured."
            call.save(update_fields=["summary"])
            return
        prompt = f"""Create a concise call summary from this transcript. Return exactly four labeled sections:
What was discussed:
What the person asked:
Their requirements:
Important points:

Transcript:
{call.transcript}
"""
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_TEXT_MODEL}:generateContent"
            response = requests.post(
                url,
                params={"key": settings.GEMINI_API_KEY},
                headers={"Content-Type": "application/json"},
                json={"contents": [{"role": "user", "parts": [{"text": prompt}]}]},
                timeout=60,
            )
            if not response.ok:
                raise RuntimeError(f"Gemini HTTP {response.status_code}: {response.text[:500]}")
            payload = response.json()
            text = ""
            for candidate in payload.get("candidates", []):
                for part in ((candidate.get("content") or {}).get("parts") or []):
                    if part.get("text"):
                        text += part["text"]
            text = text.strip()
            if not text:
                raise RuntimeError("Gemini returned an empty summary")
            call.summary = text
            labels = {
                "What was discussed:": "discussed",
                "What the person asked:": "questions",
                "Their requirements:": "requirements",
                "Important points:": "important_points",
            }
            parsed = {}
            current = None
            for line in text.splitlines():
                stripped = line.strip()
                if stripped in labels:
                    current = labels[stripped]
                    parsed[current] = []
                elif current:
                    parsed[current].append(line)
            for field in labels.values():
                value = "\n".join(parsed.get(field, [])).strip()
                if value:
                    setattr(call, field, value)
            call.save(update_fields=["summary", "discussed", "questions", "requirements", "important_points"])
            return
        except Exception as exc:
            log.exception("Gemini summary generation failed")
            person_lines = [line.split(":", 1)[1].strip() for line in call.transcript.splitlines() if line.startswith("Person:") and ":" in line]
            ai_lines = [line.split(":", 1)[1].strip() for line in call.transcript.splitlines() if line.startswith("AI:") and ":" in line]
            discussed = " ".join(ai_lines[:3]) or "The conversation was captured in the transcript."
            questions = " ".join(person_lines[:3]) or "No explicit question was captured."
            fallback = (
                f"What was discussed:\n{discussed}\n\n"
                f"What the person asked:\n{questions}\n\n"
                f"Their requirements:\n{questions}\n\n"
                f"Important points:\nGemini summary service was unavailable; see the full transcript. Provider detail: {exc}"
            )
            call.summary = fallback[:12000]
            call.discussed = discussed[:4000]
            call.questions = questions[:4000]
            call.requirements = questions[:4000]
            call.important_points = f"Gemini summary unavailable; transcript retained. {exc}"[:4000]
            call.save(update_fields=["summary", "discussed", "questions", "requirements", "important_points"])
            return

    # Optional legacy OpenAI summary path.
    if not settings.OPENAI_API_KEY:
        call.summary = "Summary unavailable because no configured AI text provider is available."
        call.save(update_fields=["summary"])
        return
    prompt = f"""Create a concise call summary from this transcript. Return exactly four labeled sections:
What was discussed:
What the person asked:
Their requirements:
Important points:

Transcript:
{call.transcript}
"""
    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}", "Content-Type": "application/json"},
            json={"model": settings.OPENAI_TEXT_MODEL, "input": prompt},
            timeout=60,
        )
        if not response.ok:
            raise RuntimeError(f"OpenAI HTTP {response.status_code}: {response.text[:500]}")
        payload = response.json()
        text = payload.get("output_text", "") or ""
        if not text:
            raise RuntimeError("OpenAI returned an empty summary")
        call.summary = text.strip()
        call.save(update_fields=["summary"])
    except Exception as exc:
        call.summary = f"Summary model unavailable. See the transcript. Provider detail: {exc}"[:12000]
        call.save(update_fields=["summary"])

def normalize_exotel_status(raw):
    value = str(raw or "").lower().replace(" ", "_")
    return {
        "queued": "QUEUED", "in_progress": "IN_PROGRESS", "ringing": "RINGING",
        "answered": "ANSWERED", "completed": "COMPLETED", "failed": "FAILED",
        "busy": "BUSY", "no_answer": "NO_ANSWER", "noanswer": "NO_ANSWER", "canceled": "CANCELED", "cancelled": "CANCELED",
    }.get(value, None)
