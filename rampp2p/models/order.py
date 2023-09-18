from django.db import models
from .ad import Ad, AdSnapshot, DurationChoices
from .peer import Peer
from .arbiter import Arbiter
from .currency import FiatCurrency, CryptoCurrency
from .payment import PaymentMethod
from datetime import timedelta

class Order(models.Model):
    ad_snapshot = models.ForeignKey(AdSnapshot, on_delete=models.PROTECT, editable=False)
    owner = models.ForeignKey(
        Peer, 
        on_delete=models.PROTECT, 
        editable=False, 
        related_name="created_orders"
    )
    
    crypto_currency = models.ForeignKey(CryptoCurrency, on_delete=models.PROTECT, editable=False)
    fiat_currency = models.ForeignKey(FiatCurrency, on_delete=models.PROTECT, editable=False)
    locked_price = models.DecimalField(max_digits=18, decimal_places=2, default=0, editable=False)
    time_duration_choice = models.IntegerField(choices=DurationChoices.choices)

    crypto_amount = models.DecimalField(max_digits=18, decimal_places=8, default=0, editable=False)
    arbiter = models.ForeignKey(
        Arbiter, 
        on_delete=models.PROTECT, 
        blank=True, 
        null=True, 
        related_name="arbitrated_orders")
    payment_methods = models.ManyToManyField(PaymentMethod)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    @property
    def time_duration(self):
        # convert the duration choice to a timedelta object
        minutes = self.time_duration_choice
        return timedelta(minutes=minutes)
