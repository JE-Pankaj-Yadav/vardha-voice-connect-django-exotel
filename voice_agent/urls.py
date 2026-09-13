from django.urls import path
from . import views

urlpatterns = [
    path("service-worker.js", views.service_worker, name="service_worker"),
    path(".well-known/appspecific/com.chrome.devtools.json", views.chrome_devtools_config, name="chrome_devtools_config"),
    path("", views.dashboard, name="dashboard"),
    path("call", views.make_call_page, name="make_call"),
    path("knowledge", views.knowledge_page, name="knowledge"),
    path("history", views.history_page, name="history"),
    path("call/<int:call_id>", views.call_detail, name="call_detail"),
    path("api/csrf", views.api_csrf, name="api_csrf"),
    path("api/call", views.api_make_call, name="api_make_call"),
    path("api/health", views.api_health, name="api_health"),
    path("api/knowledge", views.api_knowledge, name="api_knowledge"),
    path("api/knowledge/<int:item_id>", views.api_knowledge_item, name="api_knowledge_item"),
    path("api/history", views.api_history, name="api_history"),
    path("api/call/<int:call_id>", views.api_call_detail, name="api_call_detail"),
    path("api/call/<int:call_id>/recording", views.api_call_recording, name="api_call_recording"),
    path("webhooks/exotel/status", views.exotel_status_callback, name="exotel_status_callback"),
    path("webhooks/exotel/passthru", views.exotel_passthru, name="exotel_passthru"),
]
