from django.db import models


class KnowledgeItem(models.Model):
    title = models.CharField(max_length=180)
    content = models.TextField()
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    provider_checked_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["active", "updated_at"], name="kb_active_updated_idx"),
        ]

    def __str__(self):
        return self.title


class Call(models.Model):
    STATUS_CHOICES = [
        ("QUEUED", "Queued"),
        ("RINGING", "Ringing"),
        ("ANSWERED", "Answered"),
        ("IN_PROGRESS", "In progress"),
        ("COMPLETED", "Completed"),
        ("FAILED", "Failed"),
        ("BUSY", "Busy"),
        ("NO_ANSWER", "No answer"),
        ("CANCELED", "Canceled"),
    ]
    phone_number = models.CharField(max_length=30)
    exotel_sid = models.CharField(max_length=160, blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="QUEUED")
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    recording_url = models.URLField(blank=True)
    transcript = models.TextField(blank=True)
    summary = models.TextField(blank=True)
    discussed = models.TextField(blank=True)
    questions = models.TextField(blank=True)
    requirements = models.TextField(blank=True)
    important_points = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    provider_checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"], name="call_status_created_idx"),
            models.Index(fields=["exotel_sid"], name="call_exotel_sid_idx"),
        ]

    def __str__(self):
        return f"{self.phone_number} - {self.status}"
