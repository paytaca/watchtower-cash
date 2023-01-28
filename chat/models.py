from django.db import models
from psqlextra.models import PostgresModel
from main.models import Address


class ChatIdentity(PostgresModel):
    address = models.OneToOneField(
        Address,
        related_name='chat_identity',
        on_delete=models.CASCADE
    )
    user_id = models.CharField(max_length=50)
    email = models.EmailField(max_length=100)
    public_key = models.TextField()
    public_key_hash = models.CharField(max_length=70)
    signature = models.TextField()
    last_online = models.DateTimeField(blank=True, null=True)
    date_created = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Chat identities'

    def __str__(self):
        return self.email


class Conversation(PostgresModel):
    from_address = models.ForeignKey(
        Address,
        related_name='conversations_started',
        on_delete=models.CASCADE
    )
    to_address = models.ForeignKey(
        Address,
        related_name='conversations_received',
        on_delete=models.CASCADE
    )
    topic = models.TextField()
    date_created = models.DateTimeField(auto_now_add=True)
    last_messaged = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.topic

    class Meta:
        ordering = ['-last_messaged']