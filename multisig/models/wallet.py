import logging
import hashlib
import json
from django.db import models
from django.contrib.postgres.fields import JSONField


LOGGER = logging.getLogger(__name__)

class MultisigTemplate(models.Model):
    json = JSONField()
    hash = models.CharField(max_length=64, unique=True, db_index=True)

    def save(self, *args, **kwargs):
        # Canonical JSON string (sorted keys) to ensure consistent hashes
        if not self.hash:
            canonical = json.dumps(self.json, sort_keys=True)
            self.hash = hashlib.sha256(canonical.encode()).hexdigest()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.json.get("name", "Unnamed Template")


class MultisigWallet(models.Model):
    template = models.ForeignKey(MultisigTemplate, on_delete=models.PROTECT)
    locking_data = JSONField(null=True, blank=True, help_text="Raw locking data")
    created_at = models.DateTimeField(auto_now_add=True)
    locking_bytecode = models.CharField(max_length=46, null=True, blank=True)
    # created_by = models.CharField(max_length=255, null=True, blank=True, help_text="The signer's entity-key, Example: signer_1")
    
    def __str__(self):
        return self.template.json.get("name", "Unnamed Wallet")

class SignerHdPublicKey(models.Model):
    wallet = models.ForeignKey(MultisigWallet, related_name='signer_hd_public_keys', on_delete=models.CASCADE)
    key = models.CharField(max_length=255, help_text="The signer's entity-key, Example: signer_1")
    value = models.CharField(max_length=512, db_index=True, help_text="The xpub owned by the signer")

    def __str__(self):
        return f"{self.key}: {self.value}"
