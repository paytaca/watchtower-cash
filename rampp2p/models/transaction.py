
from django.db import models
from .contract import Contract

class Transaction(models.Model):
    class ActionType(models.TextChoices):
        FUND = 'FUND'
        REFUND = 'REFUND'
        ARBITER_RELEASE = 'ARBITER_RELEASE'
        SELLER_RELEASE = 'SELLER_RELEASE'

    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, editable=False)
    action = models.CharField(max_length=50, choices=ActionType.choices)
    txid = models.CharField(max_length=200, unique=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

class Recipient(models.Model):
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="recipients", editable=False)
    address = models.CharField(max_length=200, unique=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)