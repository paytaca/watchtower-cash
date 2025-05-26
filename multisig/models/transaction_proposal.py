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
    source_outputs = JSONField(null=True, blank=True, help_text="The source utxos")
    metadata = JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    # proposed_by = models.ForeignKey(Signer, blank=True, null=True)

    def __str__(self):
        return self.wallet.template.get("name", "Unnamed Wallet")
    
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

