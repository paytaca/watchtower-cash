
from django.db import models
from multisig.models.wallet import Signer, MultisigWallet

class Pst(models.Model):
    name = models.CharField(max_length=255)
    purpose = models.TextField()
    unsigned_transaction_hash = models.CharField(max_length=100, null=True, blank=True)
    unsigned_transaction_hex = models.TextField()
    signed_transaction_hex=models.TextField()
    txid = models.CharField(max_length=64, null=True, blank=True, help_text='Transaction ID after broadcast')
    wallet = models.ForeignKey(MultisigWallet, related_name='psts', on_delete=models.CASCADE)
    uploader = models.ForeignKey(Signer, on_delete=models.SET_NULL, blank=True, null=True)

    class BroadcastStatus(models.TextChoices):
        PENDING = "pending", "pending"
        CANCELLED = "cancelled", "cancelled"
        SUBMITTED = "submitted", "submitted"
        UNCONFIRMED = "unconfirmed", "unconfirmed"
        CONFIRMED = "confirmed", "confirmed"
    
    broadcast_status = models.CharField(
        max_length=20,
        choices=BroadcastStatus.choices,
        default=BroadcastStatus.PENDING
    )

class SourceOutputTokenNft(models.Model):
    capability = models.CharField(max_length=10)
    commitment = models.CharField(max_length=256, null=True, blank=True, default='')

class SourceOutputToken(models.Model):
    amount = models.DecimalField(max_digits=19, decimal_places=0, default=0)
    category = models.CharField(max_length=64)
    nft = models.OneToOneField(SourceOutputTokenNft, on_delete=models.SET_NULL, null=True, blank=True)

class SourceOutput(models.Model):
    value_satoshis = models.BigIntegerField()
    token = models.OneToOneField(SourceOutputToken, on_delete=models.SET_NULL, null=True, blank=True)
    locking_bytecode = models.CharField(max_length=150)

class Input(models.Model):
    pst = models.ForeignKey(Pst, related_name='inputs', on_delete=models.CASCADE, help_text='Input list')
    index = models.PositiveSmallIntegerField(help_text='Input index in the transaction')
    outpoint_index = models.PositiveSmallIntegerField()
    outpoint_transaction_hash = models.CharField(max_length=64)
    sequence_number = models.BigIntegerField()
    source_output = models.OneToOneField(SourceOutput, on_delete=models.SET_NULL, null=True, blank=True)
    locking_bytecode_relative_path = models.CharField(max_length=5, help_text='This is the source output\'s address relative-path')

class Output(models.Model):
    pst = models.ForeignKey(Pst, related_name='outputs', on_delete=models.CASCADE, help_text='Output list')
    index = models.PositiveSmallIntegerField(help_text='Output index in the transaction')
    locking_bytecode = models.CharField(max_length=150)
    locking_bytecode_relative_path = models.CharField(max_length=5, help_text='BIP32 path relative to the account')
    value_satoshis = models.BigIntegerField()
    token = models.OneToOneField(SourceOutputToken, on_delete=models.SET_NULL, null=True, blank=True)
    purpose = models.CharField(max_length=80, blank=True, null=True, help_text='E.g. change')

class PartialSignature(models.Model):
    signer = models.ForeignKey(Signer, on_delete=models.CASCADE)
    public_key = models.CharField(max_length=130)
    public_key_redeem_script_slot = models.PositiveSmallIntegerField(help_text='Slot of this public key on the redeem script, e.g. 1, 2, etc.')
    public_key_relative_path = models.CharField(max_length=50, help_text='BIP32 path relative to the account')
    sig_hash = models.CharField(max_length=10)
    sig_algo = models.CharField(max_length=25)
    sig = models.CharField(max_length=120)
    input = models.ForeignKey(Input, related_name='partial_signatures', on_delete=models.CASCADE)
