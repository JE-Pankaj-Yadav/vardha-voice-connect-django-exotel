from django.db import migrations


NEW_ROWS = [
    ("About Vardha Group", "Vardha Group is the company name used for this Vardha Voice Connect demonstration."),
    ("About Vardha Voice Connect", "Vardha Voice Connect is an AI voice calling assistant for practical outbound customer conversations."),
    ("Demo flow", "The demo starts with a phone number, places an outbound call, lets the AI talk with the person, answers using the Knowledge Base, and then keeps the call record for recording, transcript and summary."),
    ("Knowledge Policy", "The AI may answer factual business questions only from active Knowledge Base information. If information is unavailable, the AI must say it does not have that information and must not guess."),
    ("Natural Call Introduction", "Hello, this is Vardha Voice Connect, an AI voice assistant from Vardha Group. This is a quick demonstration call. Do you have a minute?"),
    ("AI Conversation Rules", "Speak in simple, friendly language. Keep phone answers short. If the caller speaks Hindi, answer in simple Hindi when possible; if the caller speaks English, answer in simple English. Do not guess or invent business facts."),
    ("Natural Call Closing", "Thank you for your time. This was a Vardha Voice Connect AI calling demonstration. Have a great day!"),
    ("Demo features", "The system can place an outbound call, have a live AI conversation, use Knowledge Base information, record the call, save a transcript and create a call summary."),
]


def refresh(apps, schema_editor):
    KnowledgeItem = apps.get_model("voice_agent", "KnowledgeItem")
    old_titles = [
        "Knowledge Policy", "Natural Call Closing", "Natural Call Introduction",
        "AI Conversation Rules", "How the AI Call Works", "About Vardha Group",
        "About Project Vulp", "About Vardha Voice Connect", "Demo service", "Company",
        "Demo flow", "Demo features",
    ]
    KnowledgeItem.objects.filter(title__in=old_titles).delete()
    for title, content in NEW_ROWS:
        KnowledgeItem.objects.create(title=title, content=content, active=True)


def reverse(apps, schema_editor):
    KnowledgeItem = apps.get_model("voice_agent", "KnowledgeItem")
    KnowledgeItem.objects.filter(title__in=[title for title, _ in NEW_ROWS]).delete()


class Migration(migrations.Migration):
    dependencies = [("voice_agent", "0004_indexes")]
    operations = [migrations.RunPython(refresh, reverse)]
