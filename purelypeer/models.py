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


class CashdropNftPair(models.Model):
    vault = models.ForeignKey(
        Vault,
        related_name='claim_credentials',
        on_delete=models.CASCADE
    )
    key_category = models.CharField(max_length=100 ,unique=True)
    lock_category = models.CharField(max_length=100 ,unique=True)
