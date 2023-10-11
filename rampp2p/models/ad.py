from django.db import models
from django.utils import timezone
from datetime import timedelta
from .peer import Peer
from .currency import FiatCurrency, CryptoCurrency
from .payment import PaymentMethod

class DurationChoices(models.IntegerChoices):
    FIVE_MINUTES    =   5, '5 minutes'
    FIFTEEN_MINUTES =   15, '15 minutes'
    THIRTY_MINUTES  =   30, '30 minutes'
    ONE_HOUR        =   60, '1 hour',
    FIVE_HOURS      =   300, '5 hours',
    TWELVE_HOURS    =   720, '12 hours',
    ONE_DAY         =   1440, '1 day'

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
    fixed_price = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    floating_price = models.DecimalField(max_digits=18, decimal_places=8, default=1)
    trade_floor = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    trade_ceiling = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    trade_amount = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    time_duration_choice = models.IntegerField(choices=DurationChoices.choices)
    payment_methods = models.ManyToManyField(PaymentMethod, related_name='ads')
    is_public = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    # is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return str(self.id)

    # modified for soft deletion
    def delete(self, *args, **kwargs):
        # self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save()
    
    @property
    def time_duration(self):
        # convert the duration choice to a timedelta object
        minutes = self.time_limit_choice
        return timedelta(minutes=minutes)

'''A snapshot of the ad is created everytime an order is created.'''
class AdSnapshot(models.Model):
    ad = models.ForeignKey(Ad, on_delete=models.CASCADE, related_name="snapshots")
    trade_type = models.CharField(max_length=4, choices=TradeType.choices)
    price_type = models.CharField(max_length=10, choices=PriceType.choices)
    fiat_currency = models.ForeignKey(FiatCurrency, on_delete=models.PROTECT)
    crypto_currency = models.ForeignKey(CryptoCurrency, on_delete=models.PROTECT)
    fixed_price = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    floating_price = models.DecimalField(max_digits=18, decimal_places=8, default=1)
    market_price = models.DecimalField(max_digits=18, decimal_places=8, default=1)
    trade_floor = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    trade_ceiling = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    trade_amount = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    time_duration_choice = models.IntegerField(choices=DurationChoices.choices)
    payment_methods = models.ManyToManyField(PaymentMethod, related_name='ad_snapshots') # TODO: payment_method snapshots
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return str(self.id)
    
    @property
    def time_duration(self):
        # convert the duration choice to a timedelta object
        minutes = self.time_limit_choice
        return timedelta(minutes=minutes)