from django.db import models


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
    key_category = models.CharField(max_length=100 ,unique=True)
    lock_category = models.CharField(max_length=100 ,unique=True)
    used = models.BooleanField(default=False)
    expired = models.BooleanField(default=False)
