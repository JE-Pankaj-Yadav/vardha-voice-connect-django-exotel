from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("voice_agent.urls")),
]

# Local/demo ASGI server (Daphne): explicitly serve static and media files.
# Django's runserver normally handles static files in DEBUG mode, but Daphne
# does not. STATIC_ROOT is populated by `manage.py collectstatic`.
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
