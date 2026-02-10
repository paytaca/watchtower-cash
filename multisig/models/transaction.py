from django.db import models
from multisig.models.wallet import MultisigWallet
from multisig.utils import generate_transaction_hash

class Proposal(models.Model):
    wallet = models.ForeignKey(MultisigWallet, on_delete=models.CASCADE, null=True, blank=True)
    unsigned_transaction_hex = models.TextField(help_text="The Unsigned transaction hex.")
    unsigned_transaction_hash = models.CharField(max_length=64, help_text="The hash of the Unsigned transaction")
    signed_transaction = models.TextField(null=True, blank=True, help_text="The Signed transaction hex. This could be a partially signed transaction. This updates as signing submissions are received.")
    signed_transaction_hash = models.CharField(max_length=64, null=True, blank=True, help_text="The double sha256 hash of the Signed transaction")
    proposal = models.TextField(null=True, blank=True, help_text="The serialized / encoded proposal data")
    proposal_format = models.CharField(default='psbt', max_length=50, blank=True, null=True, help_text="The format of the proposal data")

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
    redeem_script = models.TextField(blank=True, null=True)
    
    class Meta:
        unique_together = (
            'outpoint_transaction_hash',
            'outpoint_index',
        )

class Bip32Derivation(models.Model):
    input = models.ForeignKey(Input, on_delete=models.CASCADE, related_name='bip32_derivation')
    path = models.CharField(max_length=100, blank=True, null=True)
    public_key = models.CharField(max_length=66, blank=True, null=True, help_text='Signer\'s public key', unique=True)
    master_fingerprint = models.CharField(max_length=8, blank=True, null=True)

class SigningSubmission(models.Model):
    proposal = models.ForeignKey(Proposal, on_delete=models.CASCADE, related_name='signing_submissions')
    payload = models.TextField()
    payload_format = models.CharField(default='psbt', max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

class Signature(models.Model):
    input = models.ForeignKey(Input, on_delete=models.CASCADE, related_name='signatures')
    signing_submission = models.ForeignKey(SigningSubmission, on_delete=models.CASCADE, null=True, blank=True, related_name='signatures')
    public_key = models.CharField(max_length=66, help_text='Signer\'s public key')
    signature = models.CharField(max_length=160, help_text='Signature hex string')
    
