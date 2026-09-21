from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("voice_agent", "0005_refresh_demo_knowledge")]

    operations = [
        migrations.AlterField(
            model_name="call",
            name="status",
            field=models.CharField(
                choices=[
                    ("QUEUED", "Queued"),
                    ("RINGING", "Ringing"),
                    ("ANSWERED", "Answered"),
                    ("IN_PROGRESS", "In progress"),
                    ("COMPLETED", "Completed"),
                    ("FAILED", "Failed"),
                    ("BUSY", "Busy"),
                    ("NO_ANSWER", "No answer"),
                    ("CANCELED", "Canceled"),
                ],
                default="QUEUED",
                max_length=30,
            ),
        ),
    ]
