import asyncio
import base64
import json
import logging
import time

import audioop
import websockets
from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from django.utils import timezone

from .models import Call
from .services import generate_summary, system_instructions

log = logging.getLogger(__name__)


class ExotelMediaConsumer(AsyncWebsocketConsumer):
    """Exotel AgentStream <-> Gemini Live audio bridge.

    Exotel normally supplies 16-bit PCM mono telephony audio at 8 kHz.
    Gemini Live expects 16-bit PCM mono at 16 kHz and returns 24 kHz PCM.
    The bridge resamples in both directions and paces outbound Exotel media.
    """

    GEMINI_INPUT_PCM_RATE = 16000
    GEMINI_OUTPUT_PCM_RATE = 24000
    DEFAULT_EXOTEL_PCM_RATE = 8000
    EXOTEL_FRAME_MS = 100
    EXOTEL_FRAME_BYTES = 3200

    async def connect(self):
        self.call_id = self.scope["url_route"]["kwargs"]["call_id"]
        try:
            self.call = await sync_to_async(Call.objects.get)(id=int(self.call_id))
        except Exception:
            await self.close(code=4404)
            return

        await self.accept()
        self.gemini_ws = None
        self.reader_task = None
        self.stream_sid = None
        self._finished = False
        self._ai_failed = False
        self._gemini_ready = asyncio.Event()
        self._exotel_started = asyncio.Event()
        self._greeting_sent = False
        self._outbound_pcm24 = bytearray()
        self._outbound_pcm8 = bytearray()
        self._outbound_rate_state = None
        self._inbound_rate_state = None
        self._outbound_seq = 0
        self._outbound_drain_task = None
        self._outbound_pace_seconds = self.EXOTEL_FRAME_MS / 1000.0
        self._first_media_logged = False
        self._gemini_audio_seen = False
        self._exotel_sample_rate = self.DEFAULT_EXOTEL_PCM_RATE
        self._exotel_encoding = "audio/x-l16"

        await sync_to_async(self._mark_stream_connected)()
        log.info("Exotel WSS connected | call_id=%s | provider=gemini", self.call_id)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            data = json.loads(text_data or "{}")
        except json.JSONDecodeError:
            log.warning("Invalid JSON from Exotel | call_id=%s", self.call_id)
            return

        event = str(data.get("event") or "").lower()

        if event == "connected":
            return

        if event == "start":
            self.stream_sid = (
                data.get("stream_sid") or data.get("streamSid")
                or data.get("start", {}).get("stream_sid")
                or data.get("start", {}).get("streamSid")
            )
            start = data.get("start") or {}
            start_call_sid = start.get("call_sid") or start.get("callSid")
            media_format = start.get("media_format") or start.get("mediaFormat") or {}
            negotiated_rate = media_format.get("sample_rate") or media_format.get("sampleRate")
            negotiated_encoding = (
                media_format.get("encoding") or media_format.get("codec")
                or media_format.get("content_type") or media_format.get("contentType")
            )
            try:
                if negotiated_rate:
                    self._exotel_sample_rate = int(negotiated_rate)
            except (TypeError, ValueError):
                log.warning("Invalid Exotel sample rate %r; using %s", negotiated_rate, self._exotel_sample_rate)
            if negotiated_encoding:
                self._exotel_encoding = str(negotiated_encoding).lower()
            if self._exotel_sample_rate != 8000:
                log.warning("Unexpected Exotel sample rate=%s; continuing with negotiated value", self._exotel_sample_rate)
            if start_call_sid and not self.call.exotel_sid:
                self.call.exotel_sid = str(start_call_sid)
                await sync_to_async(self.call.save)(update_fields=["exotel_sid"])
            self._exotel_started.set()
            log.info(
                "Exotel event=start | call_id=%s | stream_sid=%s | call_sid=%s | encoding=%s | rate=%s",
                self.call_id, self.stream_sid, start_call_sid, self._exotel_encoding, self._exotel_sample_rate,
            )
            await self._connect_gemini()
            return

        if event == "media":
            media = data.get("media") or {}
            payload = media.get("payload") or media.get("Payload")
            if not payload or not self.gemini_ws or not self._gemini_ready.is_set():
                return
            try:
                raw_audio = base64.b64decode(payload)
                if not raw_audio:
                    return
                encoding = self._exotel_encoding
                if any(token in encoding for token in ("mulaw", "mu-law", "ulaw", "g711")):
                    pcm_native = audioop.ulaw2lin(raw_audio, 2)
                else:
                    pcm_native = raw_audio[: len(raw_audio) - (len(raw_audio) % 2)]
                if not pcm_native:
                    return
                if self._exotel_sample_rate == self.GEMINI_INPUT_PCM_RATE:
                    pcm16 = pcm_native
                else:
                    pcm16, self._inbound_rate_state = audioop.ratecv(
                        pcm_native, 2, 1, self._exotel_sample_rate,
                        self.GEMINI_INPUT_PCM_RATE, self._inbound_rate_state,
                    )
                await self.gemini_ws.send(json.dumps({
                    "realtimeInput": {
                        "audio": {
                            "data": base64.b64encode(pcm16).decode("ascii"),
                            "mimeType": f"audio/pcm;rate={self.GEMINI_INPUT_PCM_RATE}",
                        }
                    }
                }))
            except Exception as exc:
                self._ai_failed = True
                await sync_to_async(self._set_error)(f"Gemini input audio processing failed: {self._friendly_ai_error(exc)}")
                log.exception("Gemini input audio processing failed | call_id=%s", self.call_id)
            return

        if event == "stop":
            log.info("Exotel event=stop | call_id=%s", self.call_id)
            await self._finish()
            return

        if event == "clear":
            await self._clear_outbound(send_clear=False)
            return

    async def _connect_gemini(self):
        if self.gemini_ws or self._finished:
            return
        if getattr(settings, "AI_PROVIDER", "gemini") != "gemini":
            self._ai_failed = True
            await sync_to_async(self._set_error)("This build is configured for Gemini. Set AI_PROVIDER=gemini.")
            return
        if not settings.GEMINI_API_KEY:
            self._ai_failed = True
            await sync_to_async(self._set_error)("GEMINI_API_KEY is not configured. Add it to Render Environment or .env.")
            return

        try:
            url = (
                "wss://generativelanguage.googleapis.com/ws/"
                "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
                f"?key={settings.GEMINI_API_KEY}"
            )
            self.gemini_ws = await websockets.connect(
                url,
                ping_interval=20,
                ping_timeout=20,
                max_size=None,
                close_timeout=5,
            )
            self.reader_task = asyncio.create_task(self.read_gemini())

            setup = {
                "setup": {
                    "model": f"models/{settings.GEMINI_LIVE_MODEL}",
                    "responseModalities": ["AUDIO"],
                    "systemInstruction": {"parts": [{"text": system_instructions()}]},
                    "inputAudioTranscription": {},
                    "outputAudioTranscription": {},
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {"voiceName": settings.GEMINI_VOICE}
                        }
                    },
                    "realtimeInputConfig": {
                        "automaticActivityDetection": {
                            "disabled": False,
                            "prefixPaddingMs": 200,
                            "silenceDurationMs": 500,
                        }
                    },
                }
            }
            await self.gemini_ws.send(json.dumps(setup))
            log.info(
                "Gemini Live connected; waiting for setupComplete | call_id=%s | model=%s",
                self.call_id, settings.GEMINI_LIVE_MODEL,
            )
        except Exception as exc:
            self._ai_failed = True
            await sync_to_async(self._set_error)(f"Gemini Live connection failed: {self._friendly_ai_error(exc)}")
            log.exception("Gemini Live connection failed | call_id=%s", self.call_id)

    async def _maybe_send_greeting(self):
        if self._greeting_sent or not self.gemini_ws:
            return
        if not self._exotel_started.is_set() or not self._gemini_ready.is_set():
            return
        self._greeting_sent = True
        self._gemini_audio_seen = False
        try:
            await self.gemini_ws.send(json.dumps({
                "clientContent": {
                    "turns": [{
                        "role": "user",
                        "parts": [{"text": (
                            "Start the phone conversation now. Say one short, natural greeting: "
                            "Hello, this is Vardha Voice Connect, an AI voice assistant from Vardha Group. "
                            "This is a quick demonstration call. Do you have a minute? "
                            "Then listen. Do not give a long introduction."
                        )}]
                    }],
                    "turnComplete": True,
                }
            }))
            log.info("Gemini greeting requested | call_id=%s | stream_sid=%s", self.call_id, self.stream_sid)
        except Exception as exc:
            self._ai_failed = True
            await sync_to_async(self._set_error)(f"Gemini greeting failed: {self._friendly_ai_error(exc)}")
            log.exception("Gemini greeting failed | call_id=%s", self.call_id)

    async def read_gemini(self):
        try:
            async for raw in self.gemini_ws:
                data = json.loads(raw)
                if data.get("setupComplete") is not None:
                    self._gemini_ready.set()
                    log.info("Gemini setupComplete | call_id=%s", self.call_id)
                    await self._maybe_send_greeting()
                    continue

                if data.get("error"):
                    err = data.get("error") or {}
                    message = err.get("message") or str(err)
                    self._ai_failed = True
                    friendly = self._friendly_ai_error(message)
                    await sync_to_async(self._set_error)(f"Gemini Live error: {friendly}")
                    log.error("Gemini Live error | call_id=%s | error=%s", self.call_id, err)
                    continue

                server = data.get("serverContent") or {}
                if server.get("interrupted"):
                    await self._clear_outbound(send_clear=True)

                model_turn = server.get("modelTurn") or {}
                for part in model_turn.get("parts") or []:
                    inline = part.get("inlineData") or part.get("inline_data") or {}
                    audio_b64 = inline.get("data")
                    if audio_b64:
                        self._gemini_audio_seen = True
                        await self._queue_gemini_audio(audio_b64)

                input_tx = server.get("inputTranscription") or {}
                if input_tx.get("text"):
                    await sync_to_async(self._append_live_transcript)("Person", input_tx["text"].strip())

                output_tx = server.get("outputTranscription") or {}
                if output_tx.get("text"):
                    await sync_to_async(self._append_live_transcript)("AI", output_tx["text"].strip())

                if server.get("turnComplete"):
                    await self._flush_outbound()

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._ai_failed = True
            await sync_to_async(self._set_error)(f"Gemini Live stream error: {self._friendly_ai_error(exc)}")
            log.exception("Gemini reader failed | call_id=%s", self.call_id)
        finally:
            if not self._finished and self.gemini_ws is not None:
                log.warning("Gemini Live reader ended | call_id=%s | audio_seen=%s", self.call_id, self._gemini_audio_seen)

    async def _queue_gemini_audio(self, audio_b64):
        try:
            pcm24 = base64.b64decode(audio_b64)
            pcm24 = pcm24[: len(pcm24) - (len(pcm24) % 2)]
            if not pcm24:
                return
            self._outbound_pcm24.extend(pcm24)
            block_bytes = 4800  # 100 ms at 24 kHz, 16-bit mono
            while len(self._outbound_pcm24) >= block_bytes:
                block = bytes(self._outbound_pcm24[:block_bytes])
                del self._outbound_pcm24[:block_bytes]
                if self._exotel_sample_rate == self.GEMINI_OUTPUT_PCM_RATE:
                    pcm_native = block
                else:
                    pcm_native, self._outbound_rate_state = audioop.ratecv(
                        block, 2, 1, self.GEMINI_OUTPUT_PCM_RATE,
                        self._exotel_sample_rate, self._outbound_rate_state,
                    )
                if any(token in self._exotel_encoding for token in ("mulaw", "mu-law", "ulaw", "g711")):
                    pcm_native = audioop.lin2ulaw(pcm_native, 2)
                self._outbound_pcm8.extend(pcm_native)
                await self._send_ready_outbound_frames()
        except Exception as exc:
            self._ai_failed = True
            await sync_to_async(self._set_error)(f"Gemini audio conversion failed: {self._friendly_ai_error(exc)}")
            log.exception("Gemini audio conversion failed | call_id=%s", self.call_id)

    async def _send_ready_outbound_frames(self):
        if self._outbound_drain_task is None or self._outbound_drain_task.done():
            self._outbound_drain_task = asyncio.create_task(self._drain_outbound_frames())

    async def _drain_outbound_frames(self):
        try:
            while self.stream_sid and self._outbound_pcm8:
                if len(self._outbound_pcm8) < self.EXOTEL_FRAME_BYTES:
                    await asyncio.sleep(0.005)
                    continue
                frame = bytes(self._outbound_pcm8[:self.EXOTEL_FRAME_BYTES])
                del self._outbound_pcm8[:self.EXOTEL_FRAME_BYTES]
                await self._send_exotel_media(frame)
                await asyncio.sleep(self._outbound_pace_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._ai_failed = True
            await sync_to_async(self._set_error)(f"Outbound Exotel audio failed: {self._friendly_ai_error(exc)}")
            log.exception("Outbound Exotel audio drain failed | call_id=%s", self.call_id)

    async def _flush_outbound(self):
        if self._outbound_pcm24:
            block = bytes(self._outbound_pcm24)
            self._outbound_pcm24.clear()
            block = block[: len(block) - (len(block) % 2)]
            if block:
                if self._exotel_sample_rate == self.GEMINI_OUTPUT_PCM_RATE:
                    pcm_native = block
                else:
                    pcm_native, self._outbound_rate_state = audioop.ratecv(
                        block, 2, 1, self.GEMINI_OUTPUT_PCM_RATE,
                        self._exotel_sample_rate, self._outbound_rate_state,
                    )
                if any(token in self._exotel_encoding for token in ("mulaw", "mu-law", "ulaw", "g711")):
                    pcm_native = audioop.lin2ulaw(pcm_native, 2)
                self._outbound_pcm8.extend(pcm_native)
        if not self._outbound_pcm8:
            return
        tail = bytes(self._outbound_pcm8)
        self._outbound_pcm8.clear()
        target = max(self.EXOTEL_FRAME_BYTES, ((len(tail) + 319) // 320) * 320)
        tail += b"\x00" * (target - len(tail))
        for offset in range(0, len(tail), self.EXOTEL_FRAME_BYTES):
            frame = tail[offset:offset + self.EXOTEL_FRAME_BYTES]
            if len(frame) < self.EXOTEL_FRAME_BYTES:
                frame += b"\x00" * (self.EXOTEL_FRAME_BYTES - len(frame))
            await self._send_exotel_media(frame)
            await asyncio.sleep(self._outbound_pace_seconds)

    async def _send_exotel_media(self, pcm8):
        if not self.stream_sid or not pcm8:
            return
        self._outbound_seq += 1
        now_ms = int((time.monotonic() - getattr(self, "_stream_started_monotonic", time.monotonic())) * 1000)
        message = {
            "event": "media",
            "streamSid": self.stream_sid,
            "media": {
                "payload": base64.b64encode(pcm8).decode("ascii"),
                "chunk": str(self._outbound_seq),
                "timestamp": str(now_ms),
                "sequenceNumber": str(self._outbound_seq),
            },
        }
        await self.send(text_data=json.dumps(message))
        if not self._first_media_logged:
            self._first_media_logged = True
            log.info("FIRST GEMINI AUDIO SENT | call_id=%s | stream_sid=%s | bytes=%s", self.call_id, self.stream_sid, len(pcm8))

    async def _clear_outbound(self, send_clear=True):
        if self._outbound_drain_task and not self._outbound_drain_task.done():
            self._outbound_drain_task.cancel()
            try:
                await self._outbound_drain_task
            except (asyncio.CancelledError, Exception):
                pass
        self._outbound_drain_task = None
        self._outbound_pcm24.clear()
        self._outbound_pcm8.clear()
        self._outbound_rate_state = None
        if send_clear and self.stream_sid:
            try:
                await self.send(text_data=json.dumps({"event": "clear", "streamSid": self.stream_sid}))
            except Exception:
                pass

    async def disconnect(self, close_code):
        await self._finish()

    async def _finish(self):
        if self._finished:
            return
        self._finished = True
        if self.reader_task and self.reader_task is not asyncio.current_task():
            self.reader_task.cancel()
        if self.gemini_ws:
            try:
                await self.gemini_ws.close()
            except Exception:
                pass
        await sync_to_async(self._mark_completed)(self._ai_failed)
        try:
            await sync_to_async(generate_summary)(self.call.id)
        except Exception as exc:
            log.exception("Call summary generation failed | call_id=%s", self.call_id)
            await sync_to_async(self._set_error)(f"Summary generation failed: {self._friendly_ai_error(exc)}")

    def _mark_stream_connected(self):
        self._stream_started_monotonic = time.monotonic()
        if self.call.status in {"QUEUED", "RINGING", "ANSWERED"}:
            self.call.status = "IN_PROGRESS"
        if not self.call.started_at:
            self.call.started_at = timezone.now()
        if not self.call.answered_at:
            self.call.answered_at = timezone.now()
        self.call.save(update_fields=["status", "started_at", "answered_at"])

    def _append_live_transcript(self, speaker, text):
        text = str(text or "").strip()
        if not text:
            return
        line = f"{speaker}: {text}"
        current = (self.call.transcript or "").strip()
        if not current or not current.endswith(line):
            self.call.transcript = (current + "\n" + line).strip()
            self.call.save(update_fields=["transcript"])

    def _set_error(self, message):
        self.call.error_message = str(message)[:4000]
        self.call.save(update_fields=["error_message"])

    @staticmethod
    def _friendly_ai_error(exc):
        message = str(exc or "").strip()
        lower = message.lower()
        if "quota" in lower or "resource_exhausted" in lower:
            return "Gemini API quota is exhausted or the project has no available Live API quota. Check Google AI Studio/API billing and quotas."
        if "api key" in lower or "unauthorized" in lower or "permission" in lower:
            return "Gemini API key is invalid or does not have permission to use the Live API."
        return message[:1200] or "Unknown Gemini provider error"

    def _mark_completed(self, ai_failed=False):
        if ai_failed:
            self.call.status = "FAILED"
        elif self.call.status not in {"FAILED", "BUSY", "NO_ANSWER", "CANCELED"}:
            self.call.status = "COMPLETED"
        self.call.ended_at = timezone.now()
        if self.call.answered_at:
            self.call.duration_seconds = max(0, int((self.call.ended_at - self.call.answered_at).total_seconds()))
        self.call.save(update_fields=["status", "ended_at", "duration_seconds"])
