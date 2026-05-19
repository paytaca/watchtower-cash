from django.db import models


class NostrPubkey(models.Model):
    """Maps a Nostr pubkey (hex) to a wallet hash for push notification dispatch.

    One wallet hash maps to exactly one pubkey.
    """
    pubkey_hex = models.CharField(max_length=64, db_index=True)
    wallet_hash = models.CharField(max_length=70, db_index=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_active = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['pubkey_hex', 'wallet_hash']),
        ]
