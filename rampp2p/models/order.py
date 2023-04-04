from django.db import models

from .ad import Ad
from .peer import Peer
from .currency import FiatCurrency, CryptoCurrency
from .chat import Chat
from .payment import PaymentMethod

class Order(models.Order):
  ad = models.ForeignKey(Ad, on_delete=models.PROTECT, editable=False)
  creator = models.ForeignKey(Peer, on_delete=models.PROTECT, editable=False)
  crypto_currency = models.ForeignKey(CryptoCurrency, on_delete=models.PROTECT, editable=False)
  fiat_currency = models.ForeignKey(FiatCurrency, on_delete=models.PROTECT, editable=False)
  fiat_amount = models.FloatField(editable=False)
  locked_price = models.FloatField(editable=False)
  arbiter = models.ForeignKey(Peer, on_delete=models.PROTECT, blank=True, null=True)
  contract_address = models.CharField(max_length=50, blank=True, null=True)
  payment_methods = models.ManyToManyField(PaymentMethod)
  chat = models.ForeignKey(Chat, on_delete=models.SET_NULL, null=True)
  is_appealed = models.BooleanField(default=False)
  created_at = models.DateTimeField(auto_now_add=True, editable=False)
  # TODO: should not be deletable