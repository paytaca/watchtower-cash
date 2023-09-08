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


class Voucher(models.Model):
    vault = models.ForeignKey(
        Vault,
        related_name='vouchers',
        on_delete=models.CASCADE
    )
    txid = models.CharField(max_length=100, default='')
    key_category = models.CharField(max_length=100 ,unique=True)
    lock_category = models.CharField(max_length=100 ,unique=True)
    used = models.BooleanField(default=False)
    expired = models.BooleanField(default=False)
    duration_days = models.PositiveIntegerField(default=settings.UNCLAIMED_VOUCHER_EXPIRY_DAYS)
    date_created = models.DateTimeField(default=timezone.now)

    @property
    def expiration_date(self):
        expiration_date = self.date_created + timedelta(days=self.duration_days)
        return expiration_date
