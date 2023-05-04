from django.db import models

from .ad import Ad
from .peer import Peer
from .currency import FiatCurrency, CryptoCurrency
from .payment import PaymentMethod

class Order(models.Model):
    ad = models.ForeignKey(Ad, on_delete=models.PROTECT, editable=False)
    creator = models.ForeignKey(
        Peer, 
        on_delete=models.PROTECT, 
        editable=False, 
        related_name="created_orders"
    )
    crypto_currency = models.ForeignKey(CryptoCurrency, on_delete=models.PROTECT, editable=False)
    fiat_currency = models.ForeignKey(FiatCurrency, on_delete=models.PROTECT, editable=False)
    locked_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, editable=False)
    crypto_amount = models.DecimalField(max_digits=10, decimal_places=8, default=0, editable=False)
    arbiter = models.ForeignKey(
        Peer, 
        on_delete=models.PROTECT, 
        blank=True, 
        null=True, 
        related_name="arbitrated_orders")
    payment_methods = models.ManyToManyField(PaymentMethod)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

class Contract(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, editable=False)
    txid = models.CharField(max_length=100, unique=True, blank=True, null=True)
    contract_address = models.CharField(max_length=100, blank=True, null=True)
    arbiter_address = models.CharField(max_length=100, blank=True, null=True)
    buyer_address = models.CharField(max_length=100, blank=True, null=True)
    seller_address = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)