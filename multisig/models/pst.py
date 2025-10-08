
from django.db import models
from multisig.models.wallet import Signer

class Pst(models.Model):
    creator = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    purpose = models.TextField()
    unsigned_transaction_hex = models.CharField(max_length=255)
    network = models.CharField(choices=[('mainnet', 'mainnet'), ('chipnet', 'chipnet')], max_length=10)

class SourceOutputTokenNft(models.Model):
    capability = models.CharField(max_length=10)
    commitment = models.CharField(max_length=256, null=True, blank=True)

class SourceOutputToken(models.Model):
    amount = models.BigIntegerField()
    category = models.CharField(max_length=64)
    nft = models.OneToOneField(SourceOutputTokenNft, on_delete=models.SET_NULL, null=True, blank=True)

class SourceOutput(models.Model):
    # outpoint_index = models.PositiveSmallIntegerField()
    # outpoint_transaction_hash = models.CharField(max_length=64)
    value_satoshis = models.BigIntegerField()
    sequence_number = models.BigIntegerField()
    token = models.OneToOneField(SourceOutputToken, on_delete=models.SET_NULL, null=True, blank=True)
    # address_path = models.CharField(max_length=255)
    locking_bytecode = models.CharField(max_length=150)
    locking_bytecode_relative_path = models.CharField(max_length=2)

class Input(models.Model):
    pst = models.ForeignKey(Pst, on_delete=models.CASCADE)
    outpoint_index = models.PositiveSmallIntegerField()
    outpoint_transaction_hash = models.CharField(max_length=64)
    source_output = models.OneToOneField(SourceOutput, on_delete=models.SET_NULL, null=True, blank=True)

class PartialSignature(models.Model):
    signer = models.ForeignKey(Signer, on_delete=models.CASCADE)
    public_key = models.CharField(max_length=130)
    public_key_redeem_script_slot = models.PositiveSmallIntegerField(help_text='Slot of this public key on the redeem script, e.g. 1, 2, etc.')
    public_key_relative_path = models.CharField(max_length=50, help_text='BIP32 path relative to the account')
    sig_hash = models.CharField(max_length=10)
    sig_algo = models.CharField(max_length=25)
    sig = models.CharField(max_length=120)
    input = models.ForeignKey(Input, related_name='partial_signatures', on_delete=models.CASCADE)

class Output(models.Model):
    pst = models.ForeignKey(Pst, on_delete=models.CASCADE)
    locking_bytecode = models.CharField(max_length=150)
    value_satoshis = models.BigIntegerField()

