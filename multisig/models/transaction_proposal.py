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
    # proposed_by = models.ForeignKey(Signer, blank=True, null=True)

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

class MultisigTransactionProposalStatus(models.Model):
    
    class StatusChoices(models.TextChoices):
        PENDING = "pending", "Pending"
        CANCELLED = "cancelled", "Cancelled"
        BROADCASTED = "broadcasted", "Broadcasted"

    transaction_proposal = models.OneToOneField(
        MultisigTransactionProposal,
        on_delete=models.SET_NULL,
        related_name="status",
        null=True,
        blank=True,
    )
    
    transaction_hash = models.CharField(
        max_length=64,
        help_text="Computed hash of the unsigned transaction",
        unique=True
    )

    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.PENDING
    )
    
    @property
    def is_transaction_proposal_synced(self):
        return Boolean(self.transaction_proposal)

def set_status(self, status=MultisigTransactionProposalStatus.StatusChoices.PENDING):
    try:
        self.status.status = status
        self.status.save()
    except MultisigTransactionProposalStatus.DoesNotExist:
        MultisigTransactionProposalStatus.objects.create(
            transaction_proposal=self,
            transaction_hash=self.transaction_hash,
            status=status
        )

MultisigTransactionProposal.set_status = set_status
