# Vardha Voice Connect — AI Voice Calling Agent

**Release:** 1.4.1  
**Stack:** Django 5.2 · Django Channels · Daphne · Exotel AgentStream · Google Gemini Live · SQLite/PostgreSQL

Vardha Voice Connect is a focused outbound AI calling application. The operator enters a mobile number, chooses the voice for that call, places the call through Exotel, and reviews the recording, transcript, status, duration and AI-generated summary afterward.

## Core flow

**Enter Number → Outbound Call → Natural AI Conversation → Knowledge Base Answer → Recording → Transcript → Summary**

This release keeps the existing Django + Channels + Exotel + Gemini architecture and adds targeted requirement fixes rather than replacing the project stack.

## Requirement coverage

The assignment requires Hindi-first conversation, natural Hinglish/English switching, current-call context, customer interruption handling, a Knowledge Base as the single source of business truth, outbound calling, lead qualification, honest escalation, appointment/callback handling, recording, transcript, summary, database persistence, call history, graceful error handling and secure customer-data handling.

The acceptance flow and scenario list are taken from the supplied project brief.

## UI / UX direction

The interface remains branded as **Vardha Voice Connect**. It takes conceptual inspiration from Whinta Voice's operational dashboard ideas: one clear calling workspace, visible readiness, simple call setup, knowledge context, call review, status visibility and a unified history/review flow.

No Whinta source code, logo, screenshots, proprietary assets, exact wording, exact palette or exact layout are included.

Reference product: https://whinta.com/whinta-voice — used only for broad product/UX concepts such as a single calling workspace, agent/script + knowledge setup, test-before-go-live, recording/transcript review and operational visibility.

## Main features

### 1. Outbound calling

- E.164 mobile number input.
- Exotel outbound call.
- Exotel AgentStream WebSocket bridge.
- Public WSS endpoint required for real provider calls.

### 2. Per-call voice selection

The call screen provides:

- **Main Voice** → logical key `primary`
- **Female Voice** → logical key `female`

The browser sends only the logical key. The server maps it to the configured Gemini voice ID before creating the Gemini Live session.

Default configuration:

```env
GEMINI_VOICE=Kore
GEMINI_VOICE_PRIMARY=Kore
GEMINI_VOICE_FEMALE=Aoede
GEMINI_ALLOWED_VOICE_IDS=Kore,Aoede
```

Do not treat the UI labels as official provider gender classifications. They are user-facing labels for the requested project UX.

### 3. Hindi-first AI conversation

The live system prompt requires:

- natural everyday Indian Hindi by default;
- natural Hinglish when the customer mixes languages;
- English when requested or clearly preferred;
- short phone-friendly responses;
- current-call memory;
- interruption awareness;
- clarification instead of pretending to understand;
- no unnecessary repeated questions.

### 4. Knowledge Base guardrail

Only active Knowledge Base entries are placed into the runtime business-truth context.

The AI must not invent:

- prices;
- discounts;
- offers;
- availability;
- business details;
- policies;
- timelines;
- guarantees;
- contact information;
- other company facts not present in the active Knowledge Base.

When information is unavailable, the assistant should say so instead of guessing.

### 5. Call History

Call History provides:

- date/time;
- number;
- normalized status;
- duration;
- recording availability;
- summary preview;
- View action;
- Delete action.

Delete behavior:

```text
Delete → confirm number/date → DELETE /api/call/<call_id> → remove only local Call row
```

Deleting the local record does **not** claim to delete an Exotel-side recording.

### 6. Call detail

The detail page can show:

- number;
- Exotel SID;
- provider status;
- duration;
- recording player;
- transcript;
- summary sections;
- technical failure context when present.

## Project structure

```text
vardha-voice-connect-django-exotel/
├── config/
│   ├── settings.py
│   ├── asgi.py
│   └── urls.py
├── voice_agent/
│   ├── migrations/
│   ├── static/voice_agent/
│   │   ├── app.js
│   │   └── styles.css
│   ├── templates/voice_agent/
│   │   └── base_page.html
│   ├── consumers.py
│   ├── models.py
│   ├── services.py
│   ├── tests.py
│   ├── urls.py
│   └── views.py
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── render.yaml
├── requirements.txt
├── run.py
├── run.bat
├── run.sh
├── CHANGELOG_V1.4.1.md
├── FINAL_VERIFICATION_REPORT.md
├── AI_CALLING_AGENT_UPDATE_PROMPT.md
└── README.md
```

## Requirements

Use Python **3.11, 3.12 or 3.13**.

### Windows

Run:

```bat
run.bat
```

The runner creates or repairs the isolated `.venv`, installs dependencies, runs Django checks and migrations, collects static files and starts Daphne.

### macOS / Linux

Run:

```bash
chmod +x run.sh
./run.sh
```

The shell runner discovers Python 3.11/3.12/3.13 and delegates the isolated-environment setup to `run.py`.

### Manual setup

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py check
python manage.py migrate
python manage.py collectstatic --noinput
python -m daphne -b 127.0.0.1 -p 8000 config.asgi:application
```

## Environment configuration

Copy the safe template:

```text
.env.example → .env
```

Minimum real-call configuration:

```env
EXOTEL_ACCOUNT_SID=
EXOTEL_API_KEY=
EXOTEL_API_TOKEN=
EXOTEL_CALLER_ID=

GEMINI_API_KEY=
GEMINI_LIVE_MODEL=gemini-3.8-live
GEMINI_TEXT_MODEL=gemini-3.6-flash

GEMINI_VOICE=Kore
GEMINI_VOICE_PRIMARY=Kore
GEMINI_VOICE_FEMALE=Aoede
GEMINI_ALLOWED_VOICE_IDS=Kore,Aoede

EXOTEL_STREAMTYPE=bidirectional
EXOTEL_STREAM_SAMPLE_RATE=8000
EXOTEL_STREAM_AUDIO_CONTENT_TYPE=audio/x-l16;rate=8000
EXOTEL_RECORD=true

PUBLIC_BASE_URL=
HUMAN_HANDOFF_NUMBER=
```

Never commit `.env` or provider credentials.

## Local browser-only development

You can run Django locally without a live provider configuration. When `DATABASE_URL` is empty, SQLite is used.

The dashboard can still be inspected, Knowledge Base CRUD can be tested, and local API/tests can run.

## Local real-call testing

Exotel cannot connect to your machine's localhost directly. Use a public HTTPS tunnel that forwards to the local Django server.

Example:

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

Then set:

```env
PUBLIC_BASE_URL=https://your-public-tunnel.example
```

Restart the application before placing a real call.

## Render / cloud deployment

The project supports Docker and Render.

Render supplies a public hostname. When `PUBLIC_BASE_URL` is empty, the settings automatically build the public HTTPS base from `RENDER_EXTERNAL_HOSTNAME`.

The service must remain reachable over HTTPS/WSS for real Exotel AgentStream traffic.

## API endpoints

### Health

```text
GET /api/health
```

Returns real readiness information such as:

- Exotel configuration;
- Gemini configuration;
- Knowledge Base readiness;
- public WSS readiness;
- active call counts;
- configured logical voice mappings.

### Dashboard

```text
GET /api/dashboard
```

Returns real call-history counts and recent calls.

### Place call

```text
POST /api/call
Content-Type: application/json

{
  "phone_number": "+919876543210",
  "voice": "primary"
}
```

Accepted logical voice values:

```text
primary
female
```

### Call detail / delete

```text
GET    /api/call/<call_id>
DELETE /api/call/<call_id>
```

`DELETE` removes only the local application `Call` record.

### Knowledge Base

```text
GET    /api/knowledge
POST   /api/knowledge
PUT    /api/knowledge/<item_id>
DELETE /api/knowledge/<item_id>
```

## Database compatibility

The application preserves the existing SQLite/PostgreSQL approach and existing migrations.

No database reset is required for this release.

Per-call voice selection remains transient and is passed through the Exotel stream URL as a logical key. No new database column is required for voice selection.

## Gemini Live compatibility note

This release defaults to `gemini-3.8-live`, the current stable Live API model for low-latency voice-agent experiences. The previous `gemini-3.1-flash-live-preview` configuration is not the default anymore.

The live bridge continues to use the raw WebSocket architecture already present in the project. The Live session config selects a prebuilt voice using the `speechConfig → voiceConfig → prebuiltVoiceConfig → voiceName` structure.

## Provider limitation / live verification

Code-level verification and real-provider verification are different things.

A real phone call can only be verified when all of the following are available:

- valid Exotel credentials;
- valid Gemini credentials;
- a reachable public WSS endpoint;
- provider callbacks;
- an Exotel account configuration that allows the requested call.

Trial/KYC restrictions can prevent calls even when the application code is configured correctly.

## Testing commands

Run:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python manage.py test
python manage.py collectstatic --noinput
python -m compileall -q config voice_agent
bash -n run.sh
```

When Docker is available:

```bash
docker build -t vardha-voice-connect .
```

## Requirement scenarios to test

The project brief requires testing of:

1. normal customer;
2. Hindi customer;
3. Hinglish customer;
4. English customer;
5. customer interruption;
6. unclear speech;
7. repeated question;
8. topic switching;
9. angry customer;
10. interested customer;
11. not-interested customer;
12. unknown question;
13. human-transfer request;
14. disconnect/reconnect.

The code can be tested locally or with safe simulations for provider-dependent cases. Real telephony behavior must not be declared verified without a real provider run.

## Files included in the release documentation

- `CHANGELOG_V1.4.1.md` — implementation change log.
- `FINAL_VERIFICATION_REPORT.md` — commands executed and environment limitations.
- `AI_CALLING_AGENT_UPDATE_PROMPT_V4_REGRESSION_PROOF_FINAL.md` — current implementation and browser-regression execution contract.

## Security notes

- API keys remain server-side.
- Browser voice selection accepts only logical keys.
- Provider voice IDs are resolved server-side.
- Browser state-changing APIs use CSRF protection.
- Exotel webhook endpoints remain CSRF-exempt only where required by provider callbacks.
- Transcripts and Knowledge Base content are escaped before rendering.
- OTP/password/PIN/CVV are not intentionally collected by the assistant policy.
- Do not place secrets in logs, source code or Git history.

## Public deployment authentication

Admin Basic Authentication is **disabled by default** so the manager/demo deployment can open directly without a username/password. Keep `ADMIN_AUTH_ENABLED=false` on the public demo deployment.

Authentication is an optional hardening feature. To enable it intentionally, set `ADMIN_AUTH_ENABLED=true` together with `ADMIN_USERNAME` and `ADMIN_PASSWORD`. If the flag is accidentally left `true` without credentials, the middleware does not lock the whole application with a 503; it treats authentication as not configured and keeps the demo accessible. Never commit admin credentials.


## Release version

Current release: `1.4.8`

The application version is sourced only from `VERSION.txt`. Do not set `APP_VERSION` in `.env`; existing stale values are ignored.


## v1.4.4 browser rendering fix
This release makes `VERSION.txt` the sole runtime version source, removes stale application-shell caching from the service worker, and adds a local startup smoke test for HTML/JSON/CSS/JS responses.

## Render public demo (v1.4.8)

The candidate/demo Render deployment is intentionally public for review. `PUBLIC_DEMO_MODE=true` disables operator Basic Auth even if an older Render environment still contains `ADMIN_AUTH_ENABLED=true`.

For a protected deployment, set `PUBLIC_DEMO_MODE=false`, `ADMIN_AUTH_ENABLED=true`, and configure `ADMIN_USERNAME`/`ADMIN_PASSWORD`.

The container now runs `python manage.py makemigrations --check --dry-run` before migrations so model drift is detected during deployment.


## v1.4.8 migration drift fix

Added migration `0007_knowledgeitem_provider_checked_at.py` so Render `makemigrations --check --dry-run` no longer detects an unapplied model change for `KnowledgeItem.provider_checked_at`.
