from django.db import models
from rampp2p.models import Order

class Contract(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, editable=False, unique=True)
    txid = models.CharField(max_length=100, unique=True, blank=True, null=True)
    contract_address = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)