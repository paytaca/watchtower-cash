from django.db import models
from .order import Order

class Receipt(models.Model):
    txid = models.CharField(max_length=100, unique=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='order_receipts')
    created_at = models.DateTimeField(auto_now=True)