# Vardha Voice Connect v1.4.4 — QA Check

## Scope

The release was reviewed against the supplied AI Voice Calling Agent requirement PDF and the final v2.0 implementation prompt. The supplied Whinta Voice URL is used only for UX/product inspiration.

## Assignment flow

`Enter Number → Outbound Call → Natural AI Conversation → Knowledge Base Answer → Recording → Transcript → Summary`

## Implemented changes

### Calling and voice
- Per-call `Main Voice` / `Female Voice` selection.
- Browser sends only logical keys (`primary` / `female`).
- Server maps logical keys to configured Gemini voice IDs and validates them against an allow-list.
- Existing Exotel AgentStream + Gemini Live bridge remains in place.

### Conversation
- Hindi-first natural conversation policy.
- Natural Hinglish when languages are mixed.
- English when preferred/requested.
- Current-call context retention.
- Interruption and unclear-speech guidance.
- Knowledge Base as the only source of business truth.
- No invented business facts, prices, offers, timelines, guarantees or policies.

### Call history
- Per-row `View` and `Delete` actions.
- Delete confirmation includes number/date and clearly states that only the local application history record is deleted.
- `DELETE /api/call/<call_id>` returns success/404/405 as appropriate.

### Status and review
- Normalized provider/application status handling is preserved.
- AI/bridge failure is not hidden by a later provider `COMPLETED` callback.
- Recording proxy, transcript, summary and call detail remain supported.

### UX
- One Vardha operational calling workspace with readiness, real counts, recent activity, call setup, Knowledge Base and history/review flow.
- Whinta is used only for broad dashboard/product concepts; no Whinta code, logo, screenshots, exact wording, exact CSS/palette or branding is included.

## Verification results

### Passed
- Python source compilation.
- JavaScript syntax check.
- Bash `run.sh` syntax check.
- Render and Docker Compose YAML parsing.
- Source-level regression assertions in `voice_agent/tests.py` were inspected and aligned with the implemented routes/features.

### Blocked by environment
- Django management checks/tests/collectstatic/migration checks: Django is not installed and the sandbox could not reach the package index to install requirements.
- Docker image build: Docker is not installed.

## Live provider verification

Not claimed. A real phone call must be verified after deployment with real Exotel and Gemini credentials, a public WSS endpoint and provider callbacks. This is intentionally separate from local/static verification.

## v1.4.1 patch verification

- Fixed local/debug HTTP 503 caused by an old `.env` with `ADMIN_AUTH_ENABLED=true` and blank admin credentials.
- Non-debug deployments still return 503 until credentials are configured.
- `.env.example` now uses `ADMIN_AUTH_ENABLED=false` for local development.

## v1.4.4 browser regression fix
- `VERSION.txt` is authoritative for runtime versioning.
- stale `APP_VERSION` in existing `.env` is ignored.
- service worker is network-only and no longer caches app HTML/assets.
- local runner smoke-tests required content types.

## v1.4.5 Render public-demo authentication fix
- `ADMIN_AUTH_ENABLED` defaults to false.
- `render.yaml` now disables public-demo auth and does not request admin credentials.
- Missing admin credentials no longer cause a blanket HTTP 503; explicit credentials still enable Basic Auth.
- `VERSION.txt` remains the sole runtime version source.
