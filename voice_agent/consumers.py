import asyncio
import base64
import json
import logging
import time

import websockets
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from django.utils import timezone
from asgiref.sync import sync_to_async

from .models import Call
from .services import generate_summary, system_instructions

log = logging.getLogger(__name__)

import audioop



class ExotelMediaConsumer(AsyncWebsocketConsumer):
    """Exotel raw/slin 8 kHz PCM <-> OpenAI Realtime PCM 24 kHz bridge.

    Exotel AgentStream speaks 16-bit little-endian PCM at 8 kHz in both
    directions. OpenAI Realtime GA supports PCM at 24 kHz. We therefore use
    stateful audioop.ratecv resampling instead of feeding 8 kHz audio directly
    to a 24 kHz PCM session. This mirrors Exotel's current OpenAI bridge
    architecture and avoids telephone-side clicks/beeps caused by mismatched
    sample rates.
    """

    OPENAI_PCM_RATE = 24000
    DEFAULT_EXOTEL_PCM_RATE = 8000
    EXOTEL_FRAME_MS = 100
    EXOTEL_FRAME_BYTES = 3200  # Provider minimum framing; keep packets >= 3.2 KB.

    async def connect(self):
        self.call_id = self.scope["url_route"]["kwargs"]["call_id"]
        try:
            self.call = await sync_to_async(Call.objects.get)(id=int(self.call_id))
        except Exception:
            await self.close(code=4404)
            return

        await self.accept()
        self.openai_ws = None
        self.reader_task = None
        self.stream_sid = None
        self._finished = False
        self._ai_failed = False
        self._openai_session_ready = asyncio.Event()
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
        self._openai_audio_seen = False
        self._exotel_sample_rate = self.DEFAULT_EXOTEL_PCM_RATE
        self._exotel_encoding = "audio/x-l16"
        self._stream_audio_format_logged = False

        await sync_to_async(self._mark_stream_connected)()
        log.info("Exotel WSS connected | call_id=%s", self.call_id)

        # Do not open OpenAI until Exotel sends its `start` event. This is the
        # same lifecycle used by Exotel's current AgentStream/OpenAI sample and
        # prevents the bridge from starting before the stream ID/audio format
        # are known. It also removes a common source of early call failures.

    async def receive(self, text_data=None, bytes_data=None):
        try:
            data = json.loads(text_data or "{}")
        except json.JSONDecodeError:
            log.warning("Invalid JSON from Exotel | call_id=%s", self.call_id)
            return

        event = str(data.get("event") or "").lower()

        if event == "connected":
            log.info("Exotel event=connected | call_id=%s", self.call_id)
            return

        if event == "start":
            self.stream_sid = data.get("stream_sid") or data.get("streamSid") or data.get("start", {}).get("stream_sid") or data.get("start", {}).get("streamSid")
            start = data.get("start") or {}
            start_call_sid = start.get("call_sid") or start.get("callSid")
            media_format = start.get("media_format") or start.get("mediaFormat") or {}
            negotiated_rate = media_format.get("sample_rate") or media_format.get("sampleRate")
            negotiated_encoding = media_format.get("encoding") or media_format.get("codec") or media_format.get("content_type") or media_format.get("contentType")
            try:
                if negotiated_rate:
                    self._exotel_sample_rate = int(negotiated_rate)
            except (TypeError, ValueError):
                log.warning("Invalid Exotel sample rate %r; using %s", negotiated_rate, self._exotel_sample_rate)
            if negotiated_encoding:
                self._exotel_encoding = str(negotiated_encoding).lower()
            # Direct AgentStream telephony should be requested at 8 kHz. If the
            # provider reports another rate, honor the actual start event for
            # conversion but log it loudly because the URL should be 8000 Hz.
            if self._exotel_sample_rate != 8000:
                log.warning("Unexpected Exotel sample rate=%s; continuing with negotiated value", self._exotel_sample_rate)
            log.info(
                "Exotel negotiated audio | call_id=%s | encoding=%s | sample_rate=%s",
                self.call_id, self._exotel_encoding, self._exotel_sample_rate,
            )
            if start_call_sid and not self.call.exotel_sid:
                self.call.exotel_sid = str(start_call_sid)
                await sync_to_async(self.call.save)(update_fields=["exotel_sid"])
            self._exotel_started.set()
            log.info(
                "Exotel event=start | call_id=%s | stream_sid=%s | call_sid=%s | media_format=%s",
                self.call_id,
                self.stream_sid,
                start_call_sid,
                start.get("media_format") or start.get("mediaFormat"),
            )
            await self._connect_openai()
            return

        if event == "media":
            media = data.get("media") or {}
            payload = media.get("payload") or media.get("Payload")
            if not payload or not self.openai_ws:
                return
            try:
                raw_audio = base64.b64decode(payload)
                if not raw_audio:
                    return

                # AgentStream's documented default is linear PCM16 LE mono, but
                # some account configurations can negotiate another encoding.
                # Always honor the actual start.media_format instead of blindly
                # assuming 8 kHz PCM; a codec/rate mismatch produces beeps,
                # unintelligible audio, and short calls.
                encoding = self._exotel_encoding
                if "mulaw" in encoding or "mu-law" in encoding or "ulaw" in encoding or "g711" in encoding:
                    pcm_native = audioop.ulaw2lin(raw_audio, 2)
                else:
                    pcm_native = raw_audio
                    if len(pcm_native) % 2:
                        pcm_native = pcm_native[:-1]
                if not pcm_native:
                    return

                if self._exotel_sample_rate == self.OPENAI_PCM_RATE:
                    pcm24 = pcm_native
                else:
                    pcm24, self._inbound_rate_state = audioop.ratecv(
                        pcm_native,
                        2,
                        1,
                        self._exotel_sample_rate,
                        self.OPENAI_PCM_RATE,
                        self._inbound_rate_state,
                    )
                await self.openai_ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": base64.b64encode(pcm24).decode("ascii"),
                }))
            except Exception as exc:
                log.exception("Exotel input audio processing failed")
                self._ai_failed = True
                await sync_to_async(self._set_error)(f"Input audio processing failed: {exc}")
            return

        if event == "stop":
            log.info("Exotel event=stop | call_id=%s", self.call_id)
            await self._finish()
            return

        if event == "clear":
            # Exotel can send clear in bidirectional streams. Cancel any
            # currently spoken response and discard queued outbound audio.
            await self._clear_outbound()
            if self.openai_ws:
                try:
                    await self.openai_ws.send(json.dumps({"type": "response.cancel"}))
                    await self.openai_ws.send(json.dumps({"type": "input_audio_buffer.clear"}))
                except Exception:
                    pass
            return

        if event == "mark":
            log.debug("Exotel mark=%s | call_id=%s", data.get("mark"), self.call_id)

    async def _connect_openai(self):
        if self.openai_ws or self._finished:
            return
        if not settings.OPENAI_API_KEY:
            self._ai_failed = True
            await sync_to_async(self._set_error)("OPENAI_API_KEY is not configured.")
            return
        try:
            url = f"wss://api.openai.com/v1/realtime?model={settings.OPENAI_REALTIME_MODEL}"
            self.openai_ws = await websockets.connect(
                url,
                additional_headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                ping_interval=20,
                ping_timeout=20,
                max_size=None,
            )
            self.reader_task = asyncio.create_task(self.read_openai())

            session = {
                "type": "realtime",
                "instructions": system_instructions(),
                "output_modalities": ["audio"],
                "audio": {
                    "input": {
                        "format": {"type": "audio/pcm", "rate": self.OPENAI_PCM_RATE},
                        "turn_detection": {
                            "type": "server_vad",
                            "threshold": 0.6,
                            "prefix_padding_ms": 200,
                            "silence_duration_ms": 500,
                            "create_response": True,
                            "interrupt_response": True,
                        },
                        "transcription": {
                            "model": "gpt-4o-mini-transcribe",
                            "language": "en",
                        },
                    },
                    "output": {
                        "format": {"type": "audio/pcm", "rate": self.OPENAI_PCM_RATE},
                        "voice": settings.OPENAI_VOICE,
                    },
                },
            }
            await self.openai_ws.send(json.dumps({"type": "session.update", "session": session}))
            log.info(
                "OpenAI Realtime connected; waiting for session.updated | call_id=%s | model=%s",
                self.call_id, settings.OPENAI_REALTIME_MODEL,
            )
        except Exception as exc:
            self._ai_failed = True
            await sync_to_async(self._set_error)(f"OpenAI Realtime connection failed: {exc}")
            log.exception("OpenAI Realtime connection failed | call_id=%s", self.call_id)
            try:
                await self.close(code=1011)
            except Exception:
                pass

    async def _maybe_send_greeting(self):
        if self._greeting_sent or not self.openai_ws:
            return
        if not self._exotel_started.is_set() or not self._openai_session_ready.is_set():
            return
        self._greeting_sent = True
        self._openai_audio_seen = False
        try:
            # The first sentence is deliberately grounded in the seeded
            # Knowledge Base and makes the requested company/product context
            # clear before asking the caller a question.
            await self.openai_ws.send(json.dumps({
                "type": "response.create",
                "response": {
                    "output_modalities": ["audio"],
                    "instructions": (
                        "Start the phone conversation now. Say one short, natural greeting: "
                        "Hello, this is Vardha Voice Connect, an AI voice assistant from Vardha Group. "
                        "This is a quick demonstration call. Do you have a minute? "
                        "Then listen. Do not give a long introduction."
                    ),
                },
            }))
            log.info("AI greeting response.create sent | call_id=%s | stream_sid=%s", self.call_id, self.stream_sid)
        except Exception as exc:
            self._ai_failed = True
            await sync_to_async(self._set_error)(f"AI greeting failed: {exc}")
            log.exception("AI greeting failed")

    async def read_openai(self):
        try:
            async for raw in self.openai_ws:
                data = json.loads(raw)
                typ = data.get("type", "")

                if typ == "session.updated":
                    self._openai_session_ready.set()
                    log.info("OpenAI session.updated | call_id=%s", self.call_id)
                    await self._maybe_send_greeting()

                elif typ == "session.created":
                    log.info("OpenAI session.created | call_id=%s", self.call_id)

                elif typ in {"response.output_audio.delta", "response.audio.delta"}:
                    audio = data.get("delta") or ""
                    if audio:
                        self._openai_audio_seen = True
                        await self._queue_openai_audio(audio)

                elif typ in {"response.output_audio_transcript.delta", "response.audio_transcript.delta"}:
                    text = (data.get("delta") or "").strip()
                    if text:
                        await sync_to_async(self._append_live_transcript)("AI", text)

                elif typ in {"response.output_audio.done", "response.audio.done"}:
                    await self._flush_outbound()

                elif typ == "response.done":
                    await self._flush_outbound()
                    response = data.get("response") or {}
                    status = response.get("status")
                    if status and status != "completed":
                        log.warning("OpenAI response finished with status=%s | call_id=%s | response=%s", status, self.call_id, response)
                    if not self._openai_audio_seen:
                        log.warning("OpenAI response.done arrived but no audio delta has been received yet | call_id=%s", self.call_id)

                elif typ == "conversation.item.input_audio_transcription.completed":
                    text = (data.get("transcript") or "").strip()
                    if text:
                        await sync_to_async(self._append_live_transcript)("Person", text)

                elif typ == "input_audio_buffer.speech_started":
                    log.info("Caller speech started | call_id=%s", self.call_id)
                    # Barge-in: remove any unplayed AI audio so the caller can
                    # speak naturally over the agent.
                    await self._clear_outbound()

                elif typ == "input_audio_buffer.speech_stopped":
                    log.info("Caller speech stopped | call_id=%s", self.call_id)

                elif typ == "error":
                    err = data.get("error") or {}
                    message = err.get("message") or "OpenAI Realtime error"
                    code = err.get("code") or ""
                    self._ai_failed = True
                    await sync_to_async(self._set_error)(f"OpenAI {code}: {message}" if code else message)
                    log.error("OpenAI realtime error | call_id=%s | code=%s | message=%s | event=%s", self.call_id, code, message, data)

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._ai_failed = True
            await sync_to_async(self._set_error)(f"Realtime stream error: {exc}")
            log.exception("OpenAI reader failed | call_id=%s", self.call_id)
        finally:
            if not self._finished and self.openai_ws is not None:
                log.warning("OpenAI Realtime reader ended | call_id=%s | audio_seen=%s", self.call_id, self._openai_audio_seen)

    async def _queue_openai_audio(self, audio_b64):
        try:
            pcm24 = base64.b64decode(audio_b64)
            if len(pcm24) % 2:
                pcm24 = pcm24[:-1]
            if not pcm24:
                return
            self._outbound_pcm24.extend(pcm24)

            # Convert in stable blocks to preserve audioop's state between
            # chunks and prevent clicks at response-delta boundaries.
            block_bytes = 4800  # 100 ms at 24 kHz, 16-bit mono
            while len(self._outbound_pcm24) >= block_bytes:
                block = bytes(self._outbound_pcm24[:block_bytes])
                del self._outbound_pcm24[:block_bytes]
                if self._exotel_sample_rate == self.OPENAI_PCM_RATE:
                    pcm_native = block
                else:
                    pcm_native, self._outbound_rate_state = audioop.ratecv(
                        block,
                        2,
                        1,
                        self.OPENAI_PCM_RATE,
                        self._exotel_sample_rate,
                        self._outbound_rate_state,
                    )
                if "mulaw" in self._exotel_encoding or "mu-law" in self._exotel_encoding or "ulaw" in self._exotel_encoding or "g711" in self._exotel_encoding:
                    pcm_native = audioop.lin2ulaw(pcm_native, 2)
                self._outbound_pcm8.extend(pcm_native)
                await self._send_ready_outbound_frames()
        except Exception as exc:
            self._ai_failed = True
            await sync_to_async(self._set_error)(f"AI audio conversion failed: {exc}")
            log.exception("AI audio conversion failed")

    async def _send_ready_outbound_frames(self):
        # Do not burst an entire Realtime response into Exotel. Telephony must
        # receive approximately real-time media; bursting causes gaps, clicks,
        # or playback rejection. A single 100-ms frame is queued per tick.
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
            await sync_to_async(self._set_error)(f"Outbound Exotel audio failed: {exc}")
            log.exception("Outbound Exotel audio drain failed")

    async def _flush_outbound(self):
        # Process any remaining OpenAI 24k PCM, then send a single properly
        # aligned Exotel tail. Exotel recommends >=3.2k and multiples of 320.
        if self._outbound_pcm24:
            block = bytes(self._outbound_pcm24)
            self._outbound_pcm24.clear()
            if len(block) % 2:
                block = block[:-1]
            if block:
                if self._exotel_sample_rate == self.OPENAI_PCM_RATE:
                    pcm_native = block
                else:
                    pcm_native, self._outbound_rate_state = audioop.ratecv(
                        block, 2, 1, self.OPENAI_PCM_RATE, self._exotel_sample_rate, self._outbound_rate_state
                    )
                if "mulaw" in self._exotel_encoding or "mu-law" in self._exotel_encoding or "ulaw" in self._exotel_encoding or "g711" in self._exotel_encoding:
                    pcm_native = audioop.lin2ulaw(pcm_native, 2)
                self._outbound_pcm8.extend(pcm_native)

        if not self._outbound_pcm8:
            return

        tail = bytes(self._outbound_pcm8)
        self._outbound_pcm8.clear()
        target = max(self.EXOTEL_FRAME_BYTES, ((len(tail) + 319) // 320) * 320)
        if len(tail) < target:
            tail += b"\x00" * (target - len(tail))
        for offset in range(0, len(tail), self.EXOTEL_FRAME_BYTES):
            frame = tail[offset:offset + self.EXOTEL_FRAME_BYTES]
            if len(frame) < self.EXOTEL_FRAME_BYTES:
                frame += b"\x00" * (self.EXOTEL_FRAME_BYTES - len(frame))
            await self._send_exotel_media(frame)
            await asyncio.sleep(self._outbound_pace_seconds)

    async def _send_exotel_media(self, pcm8):
        if not self.stream_sid or not pcm8:
            log.warning("Skipping AI audio because Exotel stream_sid is not ready | call_id=%s", self.call_id)
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
            log.info(
                "FIRST AI AUDIO SENT | call_id=%s | stream_sid=%s | bytes=%s",
                self.call_id, self.stream_sid, len(pcm8)
            )

    async def _clear_outbound(self):
        if self._outbound_drain_task and not self._outbound_drain_task.done():
            self._outbound_drain_task.cancel()
            try:
                await self._outbound_drain_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        self._outbound_drain_task = None
        self._outbound_pcm24.clear()
        self._outbound_pcm8.clear()
        self._outbound_rate_state = None
        if self.stream_sid:
            try:
                await self.send(text_data=json.dumps({
                    "event": "clear",
                    "streamSid": self.stream_sid,
                }))
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
        if self.openai_ws:
            try:
                await self.openai_ws.close()
            except Exception:
                pass
        await sync_to_async(self._mark_completed)(self._ai_failed)
        try:
            await sync_to_async(generate_summary)(self.call.id)
        except Exception as exc:
            log.exception("Call summary generation failed | call_id=%s", self.call_id)
            await sync_to_async(self._set_error)(f"Summary generation failed: {exc}")

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
        # Transcript events can arrive in deltas. For the assignment/demo we
        # store completed transcription events and concise AI transcript text.
        line = f"{speaker}: {text}"
        current = (self.call.transcript or "").strip()
        if not current or not current.endswith(line):
            self.call.transcript = (current + "\n" + line).strip()
            self.call.save(update_fields=["transcript"])

    def _set_error(self, message):
        self.call.error_message = str(message)[:4000]
        self.call.save(update_fields=["error_message"])

    def _mark_completed(self, ai_failed=False):
        if ai_failed:
            self.call.status = "FAILED"
        elif self.call.status not in {"FAILED", "BUSY", "NO_ANSWER", "CANCELED"}:
            self.call.status = "COMPLETED"
        self.call.ended_at = timezone.now()
        if self.call.answered_at:
            self.call.duration_seconds = max(0, int((self.call.ended_at - self.call.answered_at).total_seconds()))
        self.call.save(update_fields=["status", "ended_at", "duration_seconds"])
