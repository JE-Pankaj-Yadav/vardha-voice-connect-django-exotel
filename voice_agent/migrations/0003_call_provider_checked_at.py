from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("voice_agent", "0002_seed_knowledge")]

    operations = [
        migrations.AddField(
            model_name="call",
            name="provider_checked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
