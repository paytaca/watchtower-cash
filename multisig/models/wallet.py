import logging
from django.db import models
from django.utils import timezone

LOGGER = logging.getLogger(__name__)

class MultisigWallet(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True, default=None)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(null=True, blank=True, default=0)
    created_by = models.ForeignKey('Signer', on_delete=models.SET_NULL, null=True, blank=True)

    name = models.CharField(max_length=255, help_text="The name of the wallet", null=True, blank=True)
    wallet_hash = models.CharField(max_length=70, unique=True, db_index=True, null=True, blank=True)

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save()

    def __str__(self):
        return self.name or f"Wallet {self.id}" if self.id else "Unnamed Wallet"

class Signer(models.Model):
    wallet = models.ForeignKey(MultisigWallet, related_name='signers', on_delete=models.CASCADE)
    name = models.CharField(max_length=255, help_text="Name of the signer", null=True, blank=True)
    pubkey_zero = models.CharField(max_length=66, help_text="The public key at address index 0", null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['wallet', 'pubkey_zero'], name='unique_signer')
        ]

    def __str__(self):
        return f"{self.name}: {self.pubkey_zero}"


class MultisigWalletDescriptor(models.Model):
    signer = models.ForeignKey(Signer, related_name='wallet_descriptors', on_delete=models.CASCADE)
    descriptor = models.TextField(help_text="The bsms descriptor")
