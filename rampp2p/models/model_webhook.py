from django.db import models


class ChatWebhookDelivery(models.Model):
    # ChatMessage IDs are global to the trusted chat service. Retain no message
    # content, wallet identifiers or chat-session references in the replay ledger.
    message_id = models.BigIntegerField(primary_key=True)
    expires_at = models.DateTimeField(db_index=True)
