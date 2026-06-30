from django.db import models
from django.contrib.postgres.fields import JSONField


class NostrPubkey(models.Model):
    """Maps a Nostr pubkey (hex) to a wallet hash for push notification dispatch.

    One wallet hash maps to exactly one pubkey.
    """
    pubkey_hex = models.CharField(max_length=64, db_index=True)
    wallet_hash = models.CharField(max_length=70, db_index=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_active = models.DateTimeField(null=True, blank=True)
    show_active_status = models.BooleanField(default=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['pubkey_hex', 'wallet_hash', 'last_active']),
        ]


class NostrRoom(models.Model):
    """Stores room metadata for a wallet's chat room list."""
    room_id = models.CharField(max_length=128)
    wallet_hash = models.CharField(max_length=70, db_index=True)
    type = models.CharField(max_length=10)
    name = models.CharField(max_length=255)
    members = JSONField(default=list)
    subject = models.TextField(null=True, blank=True)
    avatar = models.URLField(null=True, blank=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    last_message_timestamp = models.DateTimeField(null=True, blank=True)
    archived = models.BooleanField(default=False)

    class Meta:
        unique_together = ('wallet_hash', 'room_id')

    def __str__(self):
        return f"[{self.type}] {self.name} ({self.room_id[:16]}...)"


class NostrBlockedContact(models.Model):
    """A pubkey that the wallet has blocked from chat."""
    wallet_hash = models.CharField(max_length=70, db_index=True)
    pub_key_hex = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('wallet_hash', 'pub_key_hex')

    def __str__(self):
        return f"Blocked {self.pub_key_hex[:16]}... ({self.wallet_hash[:16]}...)"


class NostrBlockedGroup(models.Model):
    """A room that the wallet has blocked."""
    wallet_hash = models.CharField(max_length=70, db_index=True)
    room_id = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('wallet_hash', 'room_id')

    def __str__(self):
        return f"Blocked room {self.room_id[:16]}... ({self.wallet_hash[:16]}...)"
