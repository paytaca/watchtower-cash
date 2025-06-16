import logging
import hashlib
import json
from django.db import models
from django.contrib.postgres.fields import JSONField
from .wallet import MultisigWallet, Signer

LOGGER = logging.getLogger(__name__)

class MultisigTransactionProposal(models.Model):
    wallet = models.ForeignKey(MultisigWallet, on_delete=models.CASCADE)
    wallet_address_index = models.PositiveIntegerField(default=0, blank=True, null=True)
    transaction = models.TextField(help_text="Unsigned transaction hex")
    transaction_hash = models.CharField(max_length=64, help_text="Computed hash of the unsigned transaction hex", unique=True)
    source_outputs = JSONField(null=True, blank=True, help_text="The source utxos")
    metadata = JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    signed_transaction = models.TextField(null=True, blank=True, help_text="Signed transaction hex, final compilation result")
    signed_transaction_hash = models.CharField(null=True, blank=True, max_length=64, help_text="Computed hash of the signed transaction")
    txid = models.CharField(max_length=64, null=True, blank=True, help_text="Broadcasted signed transaction id", unique=True)
    # proposed_by = models.ForeignKey(Signer, blank=True, null=True)
    
    class SigningProgress(models.TextChoices):
        UNSIGNED = "unsigned", "unsigned"
        PARTIALLY_SIGNED = "partially-signed", "partially-signed"
        FULLY_SIGNED = "fully-signed", "fully-signed"
    
    signing_progress = models.CharField(
        max_length=16,
        choices=SigningProgress.choices,
        blank=True,
        null=True
    )

    class BroadcastStatus(models.TextChoices):
        PENDING = "pending", "pending"
        CANCELLED = "cancelled", "cancelled"
        DONE = "done", "done"
    
    broadcast_status = models.CharField(
        max_length=20,
        choices=BroadcastStatus.choices,
        default=BroadcastStatus.PENDING
    )
       
    def __str__(self):
        if self.metadata.get('prompt'):
            return self.metadata['prompt']
        return self.transaction_hash
    
class Signature(models.Model):
    transaction_proposal = models.ForeignKey(
        MultisigTransactionProposal,
        on_delete=models.CASCADE,
        related_name="signatures"
    )
    signer = models.ForeignKey(Signer, on_delete=models.CASCADE)
    input_index = models.PositiveSmallIntegerField()
    signature_key = models.CharField(max_length=150, help_text="Concatenated template signer variable, sig algo and sighash. Example: key1.schnorr_signature.alloutputs")
    signature_value = models.CharField(max_length=150)


