from django.db import models


class PaymentVault(models.Model):
    user_pubkey = models.CharField(max_length=75, db_index=True)
    merchant = models.ForeignKey(
        'paytacapos.Merchant',
        on_delete=models.CASCADE,
        related_name='vaults'
    )
    address = models.CharField(max_length=75, unique=True, db_index=True)
    token_address = models.CharField(max_length=75, unique=True, db_index=True)

    class Meta:
        ordering = ('merchant__name', )