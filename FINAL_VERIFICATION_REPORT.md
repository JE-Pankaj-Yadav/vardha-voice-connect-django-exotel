# Vardha Voice Connect v1.4.4 — Final Verification Report

## Purpose
This patch addresses the browser regression shown in the supplied screenshots: raw unstyled HTML and runtime/version mismatch.

## Source evidence
The supplied runtime logs showed Django checks, migrations, collectstatic and Daphne all succeeding, while the browser requested `styles.css?v=1.4.1`, `app.js?v=1.4.1`, and `service-worker.js?v=1.4.1` even though the release folder/version had already moved to 1.4.2.

## v1.4.4 changes verified statically
- `VERSION.txt` is the single source of truth.
- stale `APP_VERSION` from `.env` no longer controls runtime versioning.
- `run.py` and `run.bat` read `VERSION.txt`.
- service worker is network-only and clears old caches on activation.
- service-worker registration uses `updateViaCache: "none"`.
- frontend asset query strings come from the canonical version.
- startup smoke-test checks HTML, JSON, CSS, JS and service-worker responses.
- regression tests were updated for version consistency and service-worker behavior.

## Not claimed
A real browser session was not executable in this artifact-building environment because the project dependencies were not installed here. The user's supplied runtime evidence demonstrates the pre-fix 1.4.1 asset-version drift; the post-fix browser result must be confirmed by running v1.4.4 locally.

## v1.4.5 Render public-demo authentication fix
- `ADMIN_AUTH_ENABLED` defaults to false.
- `render.yaml` now disables public-demo auth and does not request admin credentials.
- Missing admin credentials no longer cause a blanket HTTP 503; explicit credentials still enable Basic Auth.
- `VERSION.txt` remains the sole runtime version source.
