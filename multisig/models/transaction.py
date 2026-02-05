import logging
import hashlib
import json
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import models
from django.contrib.postgres.fields import JSONField
from multisig.models.wallet import MultisigWallet, Signer
from multisig.utils import generate_transaction_hash

LOGGER = logging.getLogger(__name__)

class Proposal(models.Model):
    wallet = models.ForeignKey(MultisigWallet, on_delete=models.CASCADE, null=True, blank=True)
    purpose = models.CharField(max_length=250, blank=True, null=True, help_text="The purpose of the transaction")
    origin = models.CharField(max_length=250, blank=True, null=True, help_text="The origin of the transaction. Can be a wallet or dapp url")
    unsigned_transaction_hex = models.TextField(help_text="The Unsigned transaction hex.")
    unsigned_transaction_hash = models.CharField(max_length=64, help_text="The hash of the Unsigned transaction")
    signed_transaction = models.TextField(null=True, blank=True, help_text="The Signed transaction hex. This could be a partially signed transaction. This updates as signing submissions are received.")
    signed_transaction_hash = models.CharField(max_length=64, null=True, blank=True, help_text="The double sha256 hash of the Signed transaction")

    txid = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text="The transaction ID (txid) of the broadcasted transaction, as seen and searchable on block explorers"
    )

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
        DONE = "done", "done"
    
    broadcast_status = models.CharField(
        max_length=10,
        choices=BroadcastStatus.choices,
        default=BroadcastStatus.PENDING
    )

    def save(self, *args, **kwargs):

        if self.unsigned_transaction_hex:
            self.unsigned_transaction_hash = generate_transaction_hash(self.unsigned_transaction_hex)

        if self.signed_transaction:
            self.signed_transaction_hash = generate_transaction_hash(self.signed_transaction)

        super().save(*args, **kwargs)


class Input(models.Model):
    proposal = models.ForeignKey(Proposal, on_delete=models.CASCADE, related_name='inputs')
    outpoint_transaction_hash = models.CharField(max_length=64)
    outpoint_index = models.PositiveIntegerField()
    class Meta:
        unique_together = (
            'outpoint_transaction_hash',
            'outpoint_index',
        )
    
class SigningSubmission(models.Model):
    signer = models.ForeignKey(Signer, on_delete=models.CASCADE, related_name='signing_submissions')
    proposal = models.ForeignKey(Proposal, on_delete=models.CASCADE, related_name='signing_submissions')
    payload = models.TextField()
    payload_format = models.CharField(default='psbt', max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('proposal', 'signer')

    def save(self, *args, **kwargs):
        if self.proposal.wallet_id != self.signer.wallet_id:
            raise ValidationError(
                "Signer is not a member of the proposal's wallet"
            )
        super().save(*args, **kwargs)
