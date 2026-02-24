import hashlib
from django.db import models
from django.utils import timezone
from main.models import TransactionBroadcast
# from multisig.models.auth import ServerIdentity
from multisig.models.wallet import MultisigWallet, Signer
from multisig.utils import generate_transaction_hash

class Proposal(models.Model):
    
    wallet = models.ForeignKey(MultisigWallet, on_delete=models.CASCADE, null=True, blank=True)
    coordinator = models.ForeignKey(Signer, on_delete=models.CASCADE, null=True, blank=True) 
    unsigned_transaction_hex = models.TextField(help_text="The Unsigned transaction hex.")
    unsigned_transaction_hash = models.CharField(max_length=64, help_text="The hash of the Unsigned transaction")
    signed_transaction = models.TextField(null=True, blank=True, help_text="The Signed transaction hex. This could be a partially signed transaction. This updates as signing submissions are received.")
    signed_transaction_hash = models.CharField(max_length=64, null=True, blank=True, help_text="The double sha256 hash of the Signed transaction")
    proposal = models.TextField(null=True, blank=True, help_text="The serialized / encoded proposal data.")
    proposal_format = models.CharField(default='psbt', max_length=50, blank=True, null=True, help_text="The format of the proposal data")
    on_premise_transaction_broadcast = models.ForeignKey(TransactionBroadcast, on_delete=models.SET_NULL, null=True, blank=True, help_text="If set transaction was broadcasted thru watchtower.")
    off_premise_transaction_broadcast = models.CharField(max_length=64, null=True, blank=True, help_text="If set transaction was broadcasted outside watchtower")

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
        PENDING = "pending", "Pending"          # Proposal exists, not broadcast
        BROADCASTED = "broadcasted", "Broadcasted"  # Sent to node but not yet seen in mempool
        MEMPOOL = "mempool", "In mempool"       # Node sees tx in mempool
        CONFIRMED = "confirmed", "Confirmed"    # At least 1 confirmation
        CONFLICTED = "conflicted", "Conflicted" # Inputs spent elsewhere
        FAILED = "failed", "Failed to broadcast"
    
    broadcast_status = models.CharField(
        max_length=25,
        choices=BroadcastStatus.choices,
        default=BroadcastStatus.PENDING
    )

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"          # Proposal exists, not broadcast
        BROADCASTED = "broadcasted", "Broadcasted"  # Sent to node but not yet seen in mempool
        MEMPOOL = "mempool", "In mempool"       # Node sees tx in mempool
        CONFIRMED = "confirmed", "Confirmed"    # At least 1 confirmation
        CONFLICTED = "conflicted", "Conflicted" # Inputs spent elsewhere
        FAILED = "failed", "Failed to broadcast"
        DELETED = "deleted", "Deleted"          # Soft deleted proposal

    status = models.CharField(
        max_length=25,
        choices=Status.choices,
        default=Status.PENDING
    )

    deleted_at = models.DateTimeField(null=True, blank=True, default=None)

    def soft_delete(self):
        """
        Mark the Proposal as deleted by setting deleted_at to the current timestamp.
        """
        
        self.deleted_at = timezone.now()
        self.status = Proposal.Status.DELETED
        self.save(update_fields=["deleted_at", "status"])

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
    spending_txid = models.CharField(max_length=64, null=True, blank=True, help_text='The txid where this was spent. It could be the proposal or other tx. This can be used to invalidate the proposal as `Conflicted` or flag it as `Broadcasted`.')
    conflicting_proposal_identifier = models.CharField(max_length=64, null=True, blank=True, help_text="The unsigned transaction hash of the spending transaction that is different from the proposal.")

    class Meta:
        unique_together = (
            'proposal',
            'outpoint_transaction_hash',
            'outpoint_index',
        )

class Bip32Derivation(models.Model):
    input = models.ForeignKey(Input, on_delete=models.CASCADE, related_name='bip32_derivation')
    path = models.CharField(max_length=100, blank=True, null=True)
    public_key = models.CharField(max_length=66, blank=True, null=True, help_text='Signer\'s public key')
    master_fingerprint = models.CharField(max_length=8, blank=True, null=True)

    class Meta:
        unique_together = ('input', 'public_key')

class SigningSubmission(models.Model):
    
    proposal = models.ForeignKey(Proposal, on_delete=models.CASCADE, related_name='signing_submissions')
    payload = models.TextField()
    payload_format = models.CharField(default='psbt', max_length=50, blank=True, null=True)
    payload_hash = models.CharField(max_length=64, null=True, blank=True, help_text='The sha256 hash of the payload. Payload is treated as utf8 string. This is only used for deduplication')
    created_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def compute_payload_hash(payload):
        """
        Compute the SHA256 hash of the payload treated as a utf-8 string.
        Returns a hex digest string.
        """
        if not isinstance(payload, str):
            payload = str(payload)
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    def save(self, *args, **kwargs):
        if self.payload:
            self.payload_hash = SigningSubmission.compute_payload_hash(self.payload)
        super().save(*args, **kwargs)
        
class Signature(models.Model):
    input = models.ForeignKey(Input, on_delete=models.CASCADE, related_name='signatures')
    signing_submission = models.ForeignKey(SigningSubmission, on_delete=models.CASCADE, null=True, blank=True, related_name='signatures')
    public_key = models.CharField(max_length=66, help_text='Signer\'s public key')
    signature = models.CharField(max_length=160, help_text='Signature hex string')
    
