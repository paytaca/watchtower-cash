from django.db import models
from django.utils import timezone
from django.conf import settings

from main.models import CashNonFungibleToken

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


class Voucher(models.Model):
    vault = models.ForeignKey(
        Vault,
        related_name='vouchers',
        on_delete=models.CASCADE
    )
    value = models.FloatField(default=0.0)  # in BCH
    minting_txid = models.CharField(max_length=100, default='')
    claim_txid = models.CharField(max_length=100, null=True, blank=True)
    key_category = models.CharField(max_length=100)
    lock_category = models.CharField(max_length=100 ,unique=True)
    claimed = models.BooleanField(default=False)
    expired = models.BooleanField(default=False)
    duration_days = models.PositiveIntegerField(default=settings.UNCLAIMED_VOUCHER_EXPIRY_DAYS)
    date_created = models.DateTimeField(default=timezone.now)
    date_claimed = models.DateTimeField(null=True, blank=True)

    @property
    def expiration_date(self):
        expiration_date = self.date_created + timedelta(days=self.duration_days)
        return expiration_date

    @property
    def commitment(self):
        nft = CashNonFungibleToken.objects.filter(category=self.lock_category)
        if nft.exists():
            nft = nft.first()
            return nft.commitment
        return None
