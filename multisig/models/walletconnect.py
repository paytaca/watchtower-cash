import logging
from django.db import models
from django.contrib.postgres.fields import ArrayField, JSONField
from django.utils import timezone

from multisig.models.wallet import MultisigWallet

logger = logging.getLogger(__name__)

class WalletConnectSession(models.Model):
    """
    Represents a WalletConnect v2 session between this dApp and a wallet.
    One session can be connected to multiple accounts.
    """

    wallet = models.ForeignKey(MultisigWallet, on_delete=models.CASCADE)
    
    topic = models.CharField(
        max_length=250,
        unique=True,
        db_index=True,
        help_text="Unique WalletConnect session topic (main identifier)"
    )

    # Origin (This dApp - 'self' in WalletConnect)
    origin = JSONField(
        default=dict, 
        blank=True,
        help_text="Raw 'self' object from WalletConnect session"
    )
    origin_name = models.CharField(
        max_length=250, 
        null=True, 
        blank=True,
        help_text="Name of the dApp (from self.metadata.name)"
    )
    origin_url = models.URLField(
        max_length=500, 
        null=True, 
        blank=True,
        help_text="URL of the dApp"
    )

    peer = JSONField(
        default=dict, 
        blank=True,
        help_text="Raw 'peer' object from WalletConnect session"
    )
    peer_name = models.CharField(
        max_length=250, 
        null=True, 
        blank=True,
        db_index=True,
        help_text="Name of the connected wallet"
    )
    peer_url = models.URLField(
        max_length=500, 
        null=True, 
        blank=True,
        help_text="URL of the connected wallet"
    )

    accounts = ArrayField(
        models.CharField(max_length=255),
        default=list,
        blank=True,
        help_text="List of connected accounts/addresses"
    )

    expiry = models.BigIntegerField(
        null=True, 
        blank=True,
        help_text="Session expiry timestamp"
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Whether this session is still active"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "WalletConnect Session"
        verbose_name_plural = "WalletConnect Sessions"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['topic']),
            models.Index(fields=['peer_name']),
            models.Index(fields=['peer_url']),
            models.Index(fields=['origin_url']),
        ]
        constraints = [
            # Ensure topic is unique
            models.UniqueConstraint(
                fields=['topic'],
                name='unique_walletconnect_topic'
            ),
            # Optional: Prevent duplicate sessions with same topic + peer
            models.UniqueConstraint(
                fields=['topic', 'peer_name'],
                name='unique_topic_peer'
            ),
        ]

    def __str__(self):
        peer = self.peer_name or "Unknown Wallet"
        return f"{peer} — {self.topic[:20]}..."

    @property
    def is_expired(self) -> bool:
        """Check if session has expired"""
        if not self.expiry:
            return False
        current_timestamp = int(timezone.now().timestamp())
        return current_timestamp > self.expiry

    def save(self, *args, **kwargs):
        if self.expiry:
            current_timestamp = int(timezone.now().timestamp())
            if current_timestamp > self.expiry:
                self.is_active = False
        super().save(*args, **kwargs)