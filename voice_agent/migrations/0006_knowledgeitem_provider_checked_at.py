from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("voice_agent", "0005_refresh_demo_knowledge")]

    operations = [
        migrations.AddField(
            model_name="knowledgeitem",
            name="provider_checked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
