from django.db import migrations, models

class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="KnowledgeItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=180)),
                ("content", models.TextField()),
                ("active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-updated_at"]},
        ),
        migrations.CreateModel(
            name="Call",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("phone_number", models.CharField(max_length=30)),
                ("exotel_sid", models.CharField(blank=True, max_length=160)),
                ("status", models.CharField(choices=[("QUEUED", "Queued"), ("RINGING", "Ringing"), ("ANSWERED", "Answered"), ("IN_PROGRESS", "In progress"), ("COMPLETED", "Completed"), ("FAILED", "Failed"), ("BUSY", "Busy"), ("NO_ANSWER", "No answer")], default="QUEUED", max_length=30)),
                ("duration_seconds", models.PositiveIntegerField(blank=True, null=True)),
                ("recording_url", models.URLField(blank=True)),
                ("transcript", models.TextField(blank=True)),
                ("summary", models.TextField(blank=True)),
                ("discussed", models.TextField(blank=True)),
                ("questions", models.TextField(blank=True)),
                ("requirements", models.TextField(blank=True)),
                ("important_points", models.TextField(blank=True)),
                ("error_message", models.TextField(blank=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("answered_at", models.DateTimeField(blank=True, null=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
