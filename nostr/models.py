from django.db import models
from push_notifications.models import GCMDevice, APNSDevice


class NostrPubkeyDevice(models.Model):
    """Maps a Nostr pubkey to one or more push notification devices.

    One pubkey -> many devices (same wallet exported to multiple phones).
    One device -> many pubkeys (multiple wallets on same phone).
    """
    pubkey_hex = models.CharField(max_length=64, db_index=True)
    gcm_device = models.ForeignKey(
        GCMDevice,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='nostr_pubkeys',
    )
    apns_device = models.ForeignKey(
        APNSDevice,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='nostr_pubkeys',
    )
    wallet_hash = models.CharField(max_length=70, db_index=True)
    multi_wallet_index = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_active = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [
            ('pubkey_hex', 'gcm_device'),
            ('pubkey_hex', 'apns_device'),
        ]
        indexes = [
            models.Index(fields=['pubkey_hex', 'wallet_hash']),
        ]
