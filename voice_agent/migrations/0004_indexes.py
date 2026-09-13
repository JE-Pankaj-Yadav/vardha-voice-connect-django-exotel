from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("voice_agent", "0003_call_provider_checked_at")]

    operations = [
        migrations.AddIndex(
            model_name="knowledgeitem",
            index=models.Index(fields=["active", "updated_at"], name="kb_active_updated_idx"),
        ),
        migrations.AddIndex(
            model_name="call",
            index=models.Index(fields=["status", "created_at"], name="call_status_created_idx"),
        ),
        migrations.AddIndex(
            model_name="call",
            index=models.Index(fields=["exotel_sid"], name="call_exotel_sid_idx"),
        ),
    ]
