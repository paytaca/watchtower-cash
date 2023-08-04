from django.db import models


class Vault(models.Model):
    merchant = models.OneToOneField(
        'paytacapos.Merchant',
        related_name='vault',
        on_delete=models.CASCADE
    )

    address = models.CharField(max_length=100)
    token_address = models.CharField(max_length=100)
    receiving_pubkey = models.CharField(max_length=60)
    receiving_pubkey_hash = models.CharField(max_length=60)
