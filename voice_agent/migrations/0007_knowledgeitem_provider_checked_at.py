from django.db import migrations, models


FIELD_NAME = "provider_checked_at"


def add_provider_checked_at_if_missing(apps, schema_editor):
    """Add the column only when it is absent from an existing database.

    This migration is intentionally idempotent because some deployed databases
    already contain the column while Django's migration history does not.
    """
    KnowledgeItem = apps.get_model("voice_agent", "KnowledgeItem")
    connection = schema_editor.connection

    with connection.cursor() as cursor:
        columns = {
            column.name
            for column in connection.introspection.get_table_description(
                cursor,
                KnowledgeItem._meta.db_table,
            )
        }

    if FIELD_NAME in columns:
        return

    field = models.DateTimeField(null=True, blank=True)
    field.set_attributes_from_name(FIELD_NAME)
    schema_editor.add_field(KnowledgeItem, field)


class Migration(migrations.Migration):
    dependencies = [("voice_agent", "0006_sync_call_status_choices")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    add_provider_checked_at_if_missing,
                    reverse_code=migrations.RunPython.noop,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="knowledgeitem",
                    name=FIELD_NAME,
                    field=models.DateTimeField(blank=True, null=True),
                ),
            ],
        ),
    ]
