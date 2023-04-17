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
  fiat_amount = models.FloatField()
  locked_price = models.FloatField()
  arbiter = models.ForeignKey(
    Peer, 
    on_delete=models.PROTECT, 
    blank=True, 
    null=True, 
    related_name="arbitrated_orders")
  contract_address = models.CharField(max_length=50, blank=True, null=True)
  payment_methods = models.ManyToManyField(PaymentMethod)
  is_appealed = models.BooleanField(default=False)
  created_at = models.DateTimeField(auto_now_add=True, editable=False)
  