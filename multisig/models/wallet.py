import logging
import hashlib
from django.db import models
from django.utils import timezone
from multisig.models.auth import ServerIdentity

LOGGER = logging.getLogger(__name__)

class MultisigWallet(models.Model):
    name = models.CharField(max_length=255, help_text="The name of the wallet", null=True, blank=True)
    wallet_hash = models.CharField(max_length=255, null=True, blank=True)
    wallet_descriptor_id = models.CharField(max_length=64, null=True, blank=True, help_text="SHA256 hash of the canonical BSMS descriptor")
    version = models.PositiveIntegerField(null=True, blank=True, default=0)
    coordinator = models.ForeignKey(ServerIdentity, related_name='multisig_wallets', on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True, default=None)
    updated_at = models.DateTimeField(auto_now=True)
    # wallet_descriptor = AES-GCM encrypted bsms descryptor 

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save()

    def __str__(self):
        return self.name or self.id

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['coordinator', 'wallet_descriptor_id'], name='unique_coordinator_wallet_descriptor')
        ]

class KeyRecord(models.Model):
    publisher = models.ForeignKey(ServerIdentity, related_name='key_records_published', null=True, blank=True, on_delete=models.CASCADE)
    recipient = models.ForeignKey(ServerIdentity, related_name='key_records_received', null=True, blank=True, on_delete=models.CASCADE)
    key_record = models.TextField() # description = wallet_descriptor_id? encrypted bsms key record with ecies

class Signer(models.Model):
    name = models.CharField(max_length=255, help_text="The name of the signer", null=True, blank=True)
    master_fingerprint = models.CharField(max_length=8, help_text="The signer's xpub master fingerprint", null=True, blank=True)
    derivation_path = models.CharField(max_length=255, help_text="The derivation path of the xpub", null=True, blank=True)
    public_key = models.CharField(max_length=66, help_text="The signer's xpub public key", null=True, blank=True)
    wallet_descriptor = models.TextField(help_text="The BSMS wallet descriptor encrypted by the coordinator to this signer's public key", null=True, blank=True)
    wallet = models.ForeignKey(MultisigWallet, related_name='signers', on_delete=models.CASCADE)
    cosigner_auth_public_key = models.CharField(max_length=66, help_text="The double sha256 child non-hardened public key derived at 999/0 from this cosigner's xpub", null=True, blank=True)
    
    class Meta:
        constraints = [
                models.UniqueConstraint(fields=['wallet', 'public_key'], name='unique_signer')
            ]
    def __str__(self):
        return f"{self.entity_key}: {self.xpub}"

