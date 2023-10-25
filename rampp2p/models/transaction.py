
from django.db import models
from .contract import Contract

class Transaction(models.Model):
    class ActionType(models.TextChoices):
        ESCROW = 'ESCROW'
        REFUND = 'REFUND'
        RELEASE = 'RELEASE'
        # ARBITER_RELEASE = 'ARBITER_RELEASE'
        # SELLER_RELEASE = 'SELLER_RELEASE'

    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, editable=False)
    action = models.CharField(max_length=50, choices=ActionType.choices)
    txid = models.CharField(max_length=200, unique=True, null=True)
    valid = models.BooleanField(default=False)
    verifying = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    def __str__(self):
        return self.txid

class Recipient(models.Model):
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="recipients", editable=False)
    address = models.CharField(max_length=200)
    value = models.DecimalField(max_digits=18, decimal_places=8, default=0, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    def __str__(self):
        return str(self.id)