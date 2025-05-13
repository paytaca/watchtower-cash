from django.db import models
from django.contrib.postgres.fields import JSONField

class Signer(models.Model):
    xpub = models.CharField(max_length=120)
    name = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        unique_together = ('xpub', 'name')

class MultisigWallet(models.Model):
    m = models.IntegerField()
    n = models.IntegerField()
    name = models.CharField(max_length=120, blank=True, null=True)
    signers = models.ManyToManyField(Signer, through='MultisigWalletSigner', related_name='wallets')
    primary_multisig_address = models.CharField(max_length=120, unique=True, help_text='Multisig address derived using the shared derivation path at address index 0. Used to uniquely identify this wallet')
    derivation_path = models.CharField(max_length=120, default="m/44'/145'/0'/0", help_text='Shared BIP32 derivation path (excluding address index).')


class MultisigWalletSigner(models.Model):
    wallet = models.ForeignKey(MultisigWallet, on_delete=models.CASCADE)
    signer = models.ForeignKey(Signer, on_delete=models.CASCADE)
    signer_is_wallet_creator = models.BooleanField(default=False, help_text="True if this signer created this wallet")
    index = models.PositiveIntegerField(help_text="Position of the signer in the multisig wallet")

    class Meta:
        unique_together = ('wallet', 'index', 'signer')
        ordering = ['index']

class Transaction(models.Model):
  txid = models.CharField(max_length=64, blank=True, null=True, help_text="If present, transaction was broadcasted to the network.")
  unsigned_hex = models.TextField(unique=True)
  unsigned_hex_hash = models.TextField(unique=True, help_text="Sha256 hash of the unsigned hex")

class SignerTransactionSignature(models.Model):
  SIGNATURE_ALGOS = [
        ('ecdsa', 'ecdsa'),
        ('schnorr', 'schnorr'),
    ]
  input_index = models.IntegerField()
  transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="transaction_signatures")
  signer = models.ForeignKey(Signer, on_delete=models.CASCADE, related_name="signer_signatures")
  signature = models.CharField(max_length=200, help_text="Hex-encoded signature")
  signature_algo = models.CharField(
        max_length=10,
        choices=SIGNATURE_ALGOS,
        default='schnorr',
        help_text="Signature algorithm used (ecdsa or schnorr)"
    )
  signature_identifier = models.CharField(max_length=200, help_text="Libauth template signature placeholder key. Example: key1.schnorr_signature.all_outputs")
  sighash = models.CharField(max_length=50, null=True, blank=True)
