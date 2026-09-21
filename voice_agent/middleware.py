import base64
import hmac

from django.conf import settings
from django.http import HttpResponse


class AdminBasicAuthMiddleware:
    """Minimal optional protection for the operator dashboard/API in public deployments.

    Exotel HTTP webhooks, health checks, static files, media and the Exotel WebSocket
    endpoint are intentionally outside Django HTTP middleware or explicitly exempted.
    """

    PUBLIC_PREFIXES = (
        "/api/health",
        "/service-worker.js",
        "/static/",
        "/media/",
        "/webhooks/exotel/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _authorized(request):
        username = str(getattr(settings, "ADMIN_USERNAME", "") or "")
        password = str(getattr(settings, "ADMIN_PASSWORD", "") or "")
        header = str(request.META.get("HTTP_AUTHORIZATION", "") or "")
        if not username or not password or not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header[6:].strip(), validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return False
        if ":" not in decoded:
            return False
        supplied_user, supplied_password = decoded.split(":", 1)
        return hmac.compare_digest(supplied_user, username) and hmac.compare_digest(supplied_password, password)

    def __call__(self, request):
        enabled = bool(getattr(settings, "ADMIN_AUTH_ENABLED", False))
        if not enabled or request.path.startswith(self.PUBLIC_PREFIXES):
            return self.get_response(request)
        if self._authorized(request):
            return self.get_response(request)

        has_credentials = bool(getattr(settings, "ADMIN_USERNAME", "")) and bool(
            getattr(settings, "ADMIN_PASSWORD", "")
        )
        if not has_credentials:
            # Local/debug development must remain usable even if an old or copied
            # .env accidentally leaves ADMIN_AUTH_ENABLED=true. Public/non-debug
            # deployments still fail closed so they cannot silently run without
            # operator credentials.
            if getattr(settings, "DEBUG", False):
                return self.get_response(request)
            return HttpResponse(
                "Admin authentication is enabled, but ADMIN_USERNAME/ADMIN_PASSWORD are not configured.",
                status=503,
                content_type="text/plain; charset=utf-8",
            )
        response = HttpResponse("Authentication required.", status=401, content_type="text/plain; charset=utf-8")
        response["WWW-Authenticate"] = 'Basic realm="Vardha Voice Connect", charset="UTF-8"'
        return response
