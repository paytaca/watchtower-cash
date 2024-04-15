from django.db import models
from django.utils import timezone
from django.conf import settings

from datetime import timedelta


class Vault(models.Model):
    merchant = models.OneToOneField(
        'paytacapos.Merchant',
        related_name='vault',
        on_delete=models.CASCADE
    )
    
    # contract addresses for lock NFT storage/releasing
    address = models.CharField(max_length=100, unique=True)
    token_address = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ('merchant__name', )


class Voucher(models.Model):
    vault = models.ForeignKey(
        Vault,
        related_name='vouchers',
        on_delete=models.CASCADE
    )
    nft = models.OneToOneField(
        'main.CashNonFungibleToken',
        related_name='voucher',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    value = models.FloatField(default=0.0)  # in BCH
    minting_txid = models.CharField(max_length=100, default='')
    claim_txid = models.CharField(max_length=100, null=True, blank=True)
    category = models.CharField(max_length=100, unique=True)
    commitment = models.CharField(max_length=255, default='', blank=True)
    claimed = models.BooleanField(default=False)
    expired = models.BooleanField(default=False)
    duration_days = models.PositiveIntegerField(default=settings.UNCLAIMED_VOUCHER_EXPIRY_DAYS)
    date_created = models.DateTimeField(default=timezone.now)
    date_claimed = models.DateTimeField(null=True, blank=True)

    @property
    def expiration_date(self):
        expiration_date = self.date_created + timedelta(days=self.duration_days)
        return expiration_date
