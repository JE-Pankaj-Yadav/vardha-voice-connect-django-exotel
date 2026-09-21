# Vardha Voice Connect v1.4.7 — Verification Report

## Reason for release
The Render deployment was returning HTTP 503 for normal pages because the deployed runtime was using an older authentication configuration that still treated ADMIN_AUTH_ENABLED=true with missing credentials as a service-unavailable condition.

## v1.4.7 corrections
1. Added PUBLIC_DEMO_MODE=true to the Render Blueprint.
2. Public demo mode takes precedence over ADMIN_AUTH_ENABLED and prevents a stale Render variable from locking the dashboard.
3. Added migration 0006 to synchronize the Call.status choices, including CANCELED.
4. Explicitly named existing model indexes to match migration 0004.
5. Added makemigrations --check --dry-run to Docker startup.
6. Removed hard-coded 1.4.4 expectations from regression tests.

## Verification limits
Offline artifact environment cannot truthfully run Django integration tests because external package installation is blocked by DNS/network restrictions. The release should therefore be redeployed to Render and verified from the live URL.
