import logging
import hashlib
import json
from django.db import models
from django.contrib.postgres.fields import JSONField
from django.utils import timezone
from django.core.validators import MinValueValidator

LOGGER = logging.getLogger(__name__)

class MultisigWallet(models.Model):
    template = JSONField(help_text="Wallet template", null=True, blank=True)
    locking_data = JSONField(null=True, blank=True, help_text="Raw locking data")
    locking_bytecode = models.CharField(max_length=46, null=True, blank=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True, default=None)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(null=True, blank=True, default=0)
    created_by = models.ForeignKey('Signer', on_delete=models.SET_NULL, null=True, blank=True)

    name = models.CharField(max_length=250, default="Unnamed Multisig Wallet")
    m = models.PositiveSmallIntegerField()
    n = models.PositiveSmallIntegerField(null=True, blank=True)
    wallet_hash = models.CharField(max_length=200, help_text="The sha256 hash of the address 0 locking bytecode (The first set of lexicographically sorted public keys)")

    @property
    def required_signatures(self):
        # m = int(self.template.get('scripts')['lock']['script'].split('\n')[0].split('_')[1])
        # return m
        pass

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save()

    def __str__(self):
        return self.name

class Signer(models.Model):
    wallet = models.ForeignKey(MultisigWallet, related_name='signers', on_delete=models.CASCADE)
    entity_key = models.CharField(max_length=255, help_text="The signer's entity-key, Example: signer_1", null=True, blank=True)
    xpub = models.CharField(max_length=512, db_index=True, help_text="The xpub owned by the signer")
    name = models.CharField(max_length=200, help_text="Signers name")
    acknowledged = models.BooleanField(default=False, help_text="True if signer acknowledged the wallet")

    class Meta:
        constraints = [
                models.UniqueConstraint(fields=['wallet', 'xpub'], name='unique_signer')
            ]
    def __str__(self):
        return f"{self.entity_key}: {self.xpub}"
