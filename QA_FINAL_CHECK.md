# QA FINAL CHECK — v1.4.7

## Static/release checks
- Release version is read from VERSION.txt.
- Render Blueprint sets PUBLIC_DEMO_MODE=true and ADMIN_AUTH_ENABLED=false.
- Middleware bypasses stale admin-auth configuration in public demo mode.
- Migration 0006 synchronizes the current Call.status choices.
- Model index names match the existing migration state.
- Docker startup includes makemigrations --check --dry-run before migrate.
- No .env secrets, .venv, __pycache__ or .pyc files are packaged.

## Runtime evidence
The supplied Render logs showed the previous release was still returning 503 from /, /call and /knowledge while reporting missing admin credentials. The v1.4.7 code path removes this failure mode for the public-demo deployment. A fresh Render deploy of this exact commit is required to verify the live service.

## Provider limitation
A live Exotel/Gemini phone call is not claimed as verified without real provider credentials, provider enablement, and a reachable public WSS endpoint.
