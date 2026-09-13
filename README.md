# Vardha Voice Connect — AI Voice Calling Agent

**Version 1.0**  
**Built with:** Python, Django, Django Channels, Daphne, Exotel AgentStream, Gemini Live API, PostgreSQL/SQLite

Vardha Voice Connect is a simple web application for outbound AI phone calls. A developer can enter a mobile number, place a call, let the AI have a real phone conversation, and then review the call record.

The project follows the assignment flow:

**Enter Number → Outbound Call → AI Conversation → Knowledge Base Answer → Recording → Transcript → Summary**

The project brief requires the complete flow to work end to end, including a natural conversation, Knowledge Base answers without guessing, recording, transcript, summary and call history.

## 1. What the software does

- Place an outbound call from the web page.
- Connect Exotel AgentStream to a secure WebSocket.
- Connect the live audio stream to Gemini Live API.
- Give the caller a short Vardha Voice Connect introduction.
- Listen to the caller and continue a normal back-and-forth conversation.
- Use only active Knowledge Base information for company, product and service facts.
- Say that the information is not available instead of guessing.
- Record the call through Exotel.
- Store the conversation transcript.
- Generate a simple call summary.
- Show status, duration, recording, transcript and summary in Call History.
- Work locally with SQLite.
- Work on Render with PostgreSQL.

The Knowledge Base rule is important: the assignment says the AI must not invent facts that are not stored in the Knowledge Base.

## 2. Project name / GitHub repository

### Recommended repository name

```text
vardha-voice-connect-django-exotel
```

This name is clear, professional, and makes it easy to distinguish this Django version from an earlier implementation of the same idea.

### Application title

```text
Vardha Voice Connect — AI Voice Calling Agent
```

## 3. Simple project structure

```text
Vardha_Voice_Connect_Django_Exotel_v1.1/
│
├── config/                         # Django project settings and ASGI setup
├── voice_agent/                    # Main application
│   ├── migrations/                 # Database migrations
│   ├── static/voice_agent/         # CSS and JavaScript
│   ├── templates/voice_agent/      # Web pages
│   ├── consumers.py                # Exotel ↔ Gemini live audio bridge
│   ├── models.py                   # Calls and Knowledge Base models
│   ├── services.py                 # Exotel, Gemini and summary services
│   └── views.py                    # Web pages and APIs
│
├── data/                           # Local SQLite database folder
├── media/                          # Local media folder
├── staticfiles/                    # Collected static files
├── .env.example                    # Safe configuration template
├── .env                            # Local settings; ignored by Git
├── Dockerfile                      # Render/Docker deployment
├── docker-entrypoint.sh            # Production startup helper
├── docker-compose.yml              # Optional local Docker + PostgreSQL setup
├── render.yaml                     # Optional Render Blueprint configuration
├── run.bat                         # Easy Windows local runner
├── run.py                          # Isolated Python environment runner
├── requirements.txt                # Python dependencies
└── README.md                       # This guide
```

## 4. Local Windows setup

### Requirements

Use Python **3.11, 3.12 or 3.13**.

Run:

```bat
run.bat
```

The runner:

1. Finds a supported Python version.
2. Creates `.venv` if required.
3. Installs dependencies.
4. Runs `manage.py check`.
5. Runs database migrations.
6. Collects static files.
7. Starts Daphne on `http://127.0.0.1:8000`.

Open:

```text
http://127.0.0.1:8000
```

For a local browser-only test, SQLite is used automatically when `DATABASE_URL` is empty.

## 5. Local `.env`

The project contains `.env.example`. The Windows runner creates `.env` automatically if it does not exist.

Add your own values to `.env`:

```env
EXOTEL_ACCOUNT_SID=your-account-sid
EXOTEL_API_KEY=your-api-key
EXOTEL_API_TOKEN=your-api-token
EXOTEL_CALLER_ID=your-exophone
GEMINI_API_KEY=your-gemini-api-key
```

Do **not** put real keys into GitHub. `.env` is ignored by Git.

Render also recommends keeping secret environment variables out of source control and using the service environment settings instead.

## 6. Public WSS for local calls

The browser can open Django on localhost, but Exotel is an external service and cannot connect to your computer's `localhost` address.

For a local real-call test, use a public HTTPS tunnel:

```bat
cloudflared tunnel --url http://127.0.0.1:8000
```

Then put the HTTPS address in `.env`:

```env
PUBLIC_BASE_URL=https://your-tunnel.trycloudflare.com
```

Restart `run.bat`.

The application converts it to:

```text
wss://your-tunnel.trycloudflare.com/ws/exotel/<call-id>/?v=2&sample-rate=8000
```

The Exotel AgentStream/Gemini reference implementation also requires an externally reachable WSS endpoint and uses `sample-rate=8000` for telephony audio. It explicitly keeps the debug test tone disabled by default.

## 7. Render deployment

Render Web Services provide a public `onrender.com` address and support WebSocket connections. A Web Service must listen on `0.0.0.0`, and Render recommends using the `PORT` environment variable.

This project is prepared for Docker deployment on Render.

### Step 1 — Push to GitHub

Recommended repository:

```text
vardha-voice-connect-django-exotel
```

Before pushing:

```bat
git init
git add .
git commit -m "Initial Vardha Voice Connect Django release"
git branch -M main
git remote add origin YOUR_GITHUB_REPOSITORY_URL
git push -u origin main
```

Never run `git add .env`.

### Step 2 — Create PostgreSQL on Render

Create a **Render PostgreSQL** database.

Use the **Internal Database URL** when the web service and database are in the same Render region. Render recommends the internal connection when possible because it uses the private network and reduces latency.

### Step 3 — Create the Web Service

In Render:

**New → Web Service → connect the GitHub repository**

Choose **Docker** as the runtime so Render uses the included `Dockerfile`. Render supports building a web service directly from a Dockerfile.

### Step 4 — Environment variables

Set these in Render:

```env
DJANGO_DEBUG=false
DJANGO_SECRET_KEY=<generate-a-new-secret>
DATABASE_URL=<Render PostgreSQL Internal Database URL>

EXOTEL_ACCOUNT_SID=<your-value>
EXOTEL_API_KEY=<your-value>
EXOTEL_API_TOKEN=<your-value>
EXOTEL_CALLER_ID=<your-exophone>

GEMINI_API_KEY=<your-value>
AI_PROVIDER=gemini
GEMINI_LIVE_MODEL=gemini-3.1-flash-live-preview
GEMINI_TEXT_MODEL=gemini-3.1-flash-lite
GEMINI_VOICE=Kore

EXOTEL_STREAMTYPE=bidirectional
EXOTEL_STREAM_SAMPLE_RATE=8000
EXOTEL_STREAM_AUDIO_CONTENT_TYPE=audio/x-l16;rate=8000
EXOTEL_RECORD=true
EXOTEL_TIME_LIMIT=1800
SEND_TEST_TONE=false
```

### PUBLIC_BASE_URL on Render

You normally do **not** need to manually enter the Render URL.

Render supplies `RENDER_EXTERNAL_HOSTNAME`. This project automatically converts it to:

```text
https://<render-hostname>
```

and then creates the Exotel WebSocket URL:

```text
wss://<render-hostname>/ws/exotel/<call-id>/?v=2&sample-rate=8000
```

If you later use a custom domain, you can set `PUBLIC_BASE_URL` manually to the HTTPS custom domain.

### Step 5 — Health check

The included `render.yaml` uses:

```text
/api/health
```

as the health check path.

## 8. Database design

The application uses two main tables:

### KnowledgeItem

Stores business information used by the AI.

- title
- content
- active
- created_at
- updated_at

### Call

Stores each outbound call.

- phone number
- Exotel SID
- status
- duration
- recording URL
- transcript
- summary
- discussion
- questions
- requirements
- important points
- error message
- started time
- answered time
- ended time
- created time
- provider check time

The database also has indexes for common call-history and Knowledge Base queries.

## 9. Call status

The history screen can show:

- Queued
- Ringing
- Answered
- In progress
- Completed
- Failed
- Busy
- No answer
- Canceled

A failed or interrupted call is not incorrectly reported as a successful completed call.

The call detail page also shows the provider/AI error message when one is available.

## 10. Call history

Call History is intentionally simple.

The main screen uses a table with:

| Date & time | Number | Status | Duration | Recording | Summary | Action |
|---|---|---|---|---|---|---|
| Call time | Phone number | Current result | Minutes/seconds | Ready/Pending | Short summary | View |

Opening a call shows:

- Call details
- Call status
- Call duration
- Call outcome
- Recording player
- Full transcript
- What was discussed
- What the person asked
- Their requirements
- Important points
- Full generated summary
- Provider/AI error, when present

This matches the assignment's Call History requirement.

## 11. AI conversation rules

The AI is intentionally simple and natural.

Example opening:

> Hello, this is Vardha Voice Connect, an AI voice assistant from Vardha Group. This is a quick demonstration call. Do you have a minute?

The AI then listens instead of reading a long script.

For business questions, it uses the active Knowledge Base only.

If the information is not available, it says:

> I don't have that information right now, so I don't want to guess.

This follows the assignment's Knowledge Base rule.

## 12. Audio / beep protection

The voice bridge is designed around the current Exotel AgentStream/Gemini pattern:

- Exotel telephony audio: PCM16, 8 kHz.
- Gemini Live API audio: PCM16, 24 kHz.
- Audio is resampled locally in both directions.
- Gemini output is buffered before it is sent to Exotel.
- Exotel media frames are sent at approximately 100 ms pacing.
- Exotel `streamSid`, chunk, timestamp and sequence information are included.
- The Gemini connection starts only after Exotel's `start` event.
- No test tone is generated by this application.
- The greeting is sent only after both the Exotel stream and Gemini session are ready.

The current Exotel sample says the same important things: use `?sample-rate=8000`, keep the test tone off, wait for the Exotel start event, use GA Realtime with nested `session.audio`, and pace outbound audio.

No application can guarantee that a third-party telephony provider will never play a provider-side network/routing tone. What this project does is remove the application's own test tone and audio-format causes of clicks/beeps, and it blocks invalid public WSS configuration before a real call is placed.

## 13. Why the previous localhost error happened

The old local configuration used a placeholder public URL. Exotel cannot open a WebSocket to `localhost` on a developer's PC.

Version 1.0 fixes this in two ways:

- Local: use `PUBLIC_BASE_URL=https://...` from a public tunnel.
- Render: automatically use `RENDER_EXTERNAL_HOSTNAME`.

If no public WSS is available, the Call button remains blocked instead of creating a call that cannot reach the AI bridge.

## 14. Docker check

The Dockerfile:

1. Uses Python 3.13.
2. Installs all required Python packages.
3. Copies the application.
4. Creates runtime folders.
5. Runs migrations when the container starts.
6. Runs `collectstatic` when the container starts.
7. Starts Daphne on `0.0.0.0`.
8. Uses Render's `PORT` value and falls back to `10000`.

This is important because Render requires a web service to bind to `0.0.0.0` and recommends the `PORT` environment variable.

## 15. Local SQLite vs Render PostgreSQL

### Local

If `DATABASE_URL` is empty:

```text
SQLite → data/db.sqlite3
```

### Render

If `DATABASE_URL` is set:

```text
Render PostgreSQL → Django ORM
```

The same Django models and migrations are used in both environments.

Render's Django deployment guidance recommends PostgreSQL plus `DATABASE_URL` for production deployments.

## 16. Troubleshooting in simple words

### Call button says Public WSS required

Local:

```env
PUBLIC_BASE_URL=https://your-tunnel-url
```

Render:

- Leave `PUBLIC_BASE_URL` empty.
- Confirm the Render service is running.
- Confirm `RENDER_EXTERNAL_HOSTNAME` is present.

### Exotel authentication error

Check:

```text
EXOTEL_ACCOUNT_SID
EXOTEL_API_KEY
EXOTEL_API_TOKEN
```

### Invalid From / destination error

For a trial Exotel account, the destination may need to be added and verified before outbound API testing is allowed.

### AI does not speak

Check Render logs for these messages:

```text
Exotel event=start
Gemini Live API connected
Gemini session.updated
AI greeting response.create sent
FIRST AI AUDIO SENT
```

If `Exotel event=start` never appears, the public WSS/Exotel AgentStream connection is the first thing to check.

If `session.updated` never appears, check the Gemini key, model and Realtime access.

If `FIRST AI AUDIO SENT` appears but the phone is silent, check the Exotel AgentStream account/feature configuration and provider media protocol.

### Recording is pending

Exotel may need time to prepare the recording. The application checks the provider again when the call detail page is opened.

## 17. Important external services

The application code can be tested locally without placing a real call, but a real end-to-end voice call depends on:

- Exotel account and outbound-call permission.
- Exotel Connect Voice AI / AgentStream availability for the account.
- A reachable public WSS endpoint.
- Gemini Live API access and API key.
- A valid Exotel destination and ExoPhone.

The Exotel Agent-Stream project describes the same prerequisites: Exotel AgentStream/Voicebot enabled, provider API key and public WSS.

## 18. Assignment compliance

The project is kept deliberately simple rather than adding unnecessary features. The assignment itself says the main goal is a simple, clean and properly working system, with the complete flow working from start to finish.

The implemented flow is:

```text
Enter number
    ↓
Outbound Exotel call
    ↓
Person answers
    ↓
Secure AgentStream WSS
    ↓
Gemini Live API conversation
    ↓
Knowledge Base answers
    ↓
Call recording
    ↓
Transcript
    ↓
Call summary
    ↓
Call history
```

## 19. Final developer checklist

Before the demo:

- [ ] Run the project locally.
- [ ] Open Dashboard, Call someone, Business information and Call history.
- [ ] Add clear Vardha Group facts to the Knowledge Base.
- [ ] Add only information that the AI is allowed to say.
- [ ] Confirm `OPENAI_API_KEY` is set.
- [ ] Confirm Exotel credentials are set.
- [ ] Confirm the ExoPhone is correct.
- [ ] For local real calls, confirm the public tunnel is running.
- [ ] For Render, confirm the web service is healthy.
- [ ] Confirm Render PostgreSQL is connected.
- [ ] Make one test call.
- [ ] Confirm the greeting is heard.
- [ ] Ask one Knowledge Base question.
- [ ] Ask one question that is not in the Knowledge Base and confirm the AI does not guess.
- [ ] End the call.
- [ ] Open Call History.
- [ ] Confirm duration, status, recording, transcript and summary.
- [ ] Record the complete demo video.
- [ ] Push the final source to GitHub.

The assignment specifically requires a working demo video and a GitHub repository link for evaluation.


## Gemini Live provider (v1.1)

This release uses Gemini Live as the default real-time voice provider. The backend keeps the API key server-side and connects from Django/Daphne to Gemini over a server-to-server WebSocket. Gemini Live expects 16-bit PCM mono at 16 kHz and returns 24 kHz PCM audio; the Exotel bridge performs the required 8 kHz telephony conversions and paces outbound media. The current Gemini Live WebSocket endpoint and message format follow Google's Live API documentation.

Render environment variables:

```text
AI_PROVIDER=gemini
GEMINI_API_KEY=<your-key>
GEMINI_LIVE_MODEL=gemini-3.1-flash-live-preview
GEMINI_TEXT_MODEL=gemini-3.1-flash-lite
GEMINI_VOICE=Kore
```

Google currently lists Gemini 3.1 Flash Live Preview with free-tier input/output pricing, subject to the account/project's quota and availability. A free-tier key is not a guarantee of unlimited Live API usage; check Google AI Studio quotas if a call returns `RESOURCE_EXHAUSTED`.

After deploying v1.1 on Render, replace the old `OPENAI_API_KEY` environment variable with `GEMINI_API_KEY`, keep `AI_PROVIDER=gemini`, and redeploy. Do not paste API keys into GitHub.


## v1.2.0 live-audio reliability fix

This release fixes the remaining silent-call failure modes found during the real Exotel test.

- Uses the current Gemini Live `generationConfig.responseModalities=["AUDIO"]` shape and places the voice configuration under `generationConfig`.
- Buffers up to 3 seconds of caller PCM while Gemini is completing `setupComplete`, instead of silently dropping the first caller words.
- Flushes buffered caller audio immediately after the Gemini session becomes ready.
- Adds a 12-second Gemini setup watchdog and a 10-second no-AI-audio watchdog so a silent provider failure is recorded as `FAILED` with a useful error instead of appearing as a normal completed call.
- Keeps the Exotel AgentStream media protocol at 100 ms / 3200-byte chunks for 8 kHz and uses the configured sample rate in the public stream URL. Exotel documents raw/slin 16-bit little-endian mono audio and bidirectional media playback for Voicebot/AgentStream.
- Adds explicit logs for `setupComplete`, buffered audio flush, and `FIRST GEMINI AUDIO SENT`.
- Bumps the service-worker cache and release version to `1.2.0`.

### Required Render settings for this release

Set `APP_VERSION=1.2.0`, `AI_PROVIDER=gemini`, `GEMINI_LIVE_MODEL=gemini-3.1-flash-live-preview`, `EXOTEL_STREAMTYPE=bidirectional`, `EXOTEL_STREAM_SAMPLE_RATE=8000`, and `EXOTEL_RECORD=true`.

After deployment, a successful call must show these Render log checkpoints in order:

1. `Exotel event=start`
2. `Gemini Live connected; waiting for setupComplete`
3. `Gemini setupComplete`
4. `Gemini greeting requested`
5. `FIRST GEMINI AUDIO SENT`

If checkpoint 3 is missing, the issue is Gemini authentication/model/quota/network. If checkpoint 3 exists but checkpoint 5 is missing, Gemini generated no audio and the new watchdog will record the exact failure stage. If checkpoint 5 exists but the caller still hears silence, the issue is on the Exotel bidirectional playback leg and the outgoing `media` payload must be inspected.

## v1.1.1 stability fix

- Fixed the Gemini Live startup crash caused by synchronous Django ORM access from the ASGI async consumer.
- The Knowledge Base is now loaded through `sync_to_async` before the Gemini Live session is configured.
- Preserved application-level Gemini/AI failures in call history even when Exotel later reports the telephony leg as `COMPLETED`.
- Health now reports active Knowledge Base readiness.
- Added support for logging Gemini interim input transcription without polluting the final transcript.

## Exotel trial limitation

An Exotel trial/KYC restriction cannot be bypassed by application code. If Exotel only permits calls to verified destinations on the current account, unverified destinations must be verified or the account must be enabled for broader outbound calling before those calls can be placed.
