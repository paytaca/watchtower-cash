from django.db import models
from django.utils import timezone

from .peer import Peer
from .currency import FiatCurrency, CryptoCurrency
from .payment import PaymentMethod

class TradeType(models.TextChoices):
    SELL = 'SELL'
    BUY = 'BUY'

class PriceType(models.TextChoices):
    FIXED = 'FIXED'
    FLOATING = 'FLOATING'

class Ad(models.Model):
    owner = models.ForeignKey(Peer, on_delete=models.PROTECT)
    trade_type = models.CharField(max_length=4, choices=TradeType.choices)
    price_type = models.CharField(max_length=10, choices=PriceType.choices)
    fiat_currency = models.ForeignKey(FiatCurrency, on_delete=models.PROTECT)
    crypto_currency = models.ForeignKey(CryptoCurrency, on_delete=models.PROTECT)
    fixed_price = models.FloatField(null=True)
    floating_price = models.FloatField(null=True)
    trade_floor = models.FloatField()
    trade_ceiling = models.FloatField()
    crypto_amount = models.FloatField()
    time_limit = models.IntegerField()
    payment_methods = models.ManyToManyField(PaymentMethod, related_name='ads')
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(blank=True, null=True)

    # modified for soft deletion
    def delete(self, *args, **kwargs):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save()

    # class Meta:
    #   # Exclude deleted records by default
    #   # Use `MyModel.all_objects` to retrieve all records
    #   default_manager_name = 'objects'
    #   ordering = ['-id']

    # objects = models.Manager()
    # all_objects = models.Manager.with_deleted()



