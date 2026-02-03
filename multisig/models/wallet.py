import logging
from django.db import models
from django.utils import timezone
from multisig.models.coordinator import ServerIdentity

LOGGER = logging.getLogger(__name__)

class MultisigWallet(models.Model):
    # template = JSONField(help_text="Wallet template")
    # locking_data = JSONField(null=True, blank=True, help_text="Raw locking data")
    # locking_bytecode = models.CharField(max_length=46, null=True, blank=True, unique=True)
    name = models.CharField(max_length=255, help_text="The name of the wallet", null=True, blank=True)
    wallet_hash = models.CharField(max_length=255, null=True, blank=True)
    wallet_descriptor_id = models.CharField(max_length=64, null=True, blank=True, help_text="SHA256 hash of the canonical BSMS descriptor")
    version = models.PositiveIntegerField(null=True, blank=True, default=0)
    coordinator = models.ForeignKey(ServerIdentity, related_name='multisig_wallets', on_delete=models.CASCADE, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True, default=None)
    updated_at = models.DateTimeField(auto_now=True)
    
    
    # created_by = models.ForeignKey('Signer', on_delete=models.SET_NULL, null=True, blank=True)
    # @property
    # def required_signatures(self):
    #     m = int(self.template.get('scripts')['lock']['script'].split('\n')[0].split('_')[1])
    #     return m

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save()

    def __str__(self):
        return self.get("name")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['coordinator', 'wallet_descriptor_id'], name='unique_coordinator_wallet_descriptor')
        ]

class Signer(models.Model):

    name = models.CharField(max_length=255, help_text="The name of the signer", null=True, blank=True)
    master_fingerprint = models.CharField(max_length=8, help_text="The signer's xpub master fingerprint", null=True, blank=True)
    derivation_path = models.CharField(max_length=255, help_text="The derivation path of the xpub", null=True, blank=True)
    public_key = models.CharField(max_length=66, help_text="The signer's xpub public key", null=True, blank=True)
    wallet_descriptor = models.TextField(help_text="The BSMS wallet descriptor encrypted by the coordinator to this signer's public key", null=True, blank=True)
    wallet = models.ForeignKey(MultisigWallet, related_name='signers', on_delete=models.CASCADE)
    
    
    # derivation_path = models.CharField(max_length=255, help_text="The derivation path of the signer", null=True, blank=True)
    # entity_key = models.CharField(max_length=255, help_text="The signer's entity-key, Example: signer_1")
    # xpub = models.CharField(max_length=512, db_index=True, help_text="The xpub owned by the signer")
    # acknowledged = models.BooleanField(default=False, help_text="True if signer acknowledged the wallet")

    class Meta:
        constraints = [
                models.UniqueConstraint(fields=['wallet', 'public_key'], name='unique_signer')
            ]
    def __str__(self):
        return f"{self.entity_key}: {self.xpub}"

