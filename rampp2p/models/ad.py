from django.db import models
from django.utils import timezone
from django.apps import apps

from datetime import timedelta

from .peer import Peer
from .currency import FiatCurrency, CryptoCurrency
from .payment import PaymentMethod, PaymentType

class CooldownChoices(models.IntegerChoices):
    FIFTEEN     =   15, '15 minutes'
    THIRTY      =   30, '30 minutes'
    FORTY_FIVE  =   45, '45 minutes'
    SIXTY       =   60, '60 minutes'

class TradeType(models.TextChoices):
    SELL = 'SELL'
    BUY = 'BUY'

class PriceType(models.TextChoices):
    FIXED = 'FIXED'
    FLOATING = 'FLOATING'

class Ad(models.Model):
    owner = models.ForeignKey(Peer, on_delete=models.PROTECT)
    trade_type = models.CharField(max_length=4, choices=TradeType.choices, db_index=True)
    price_type = models.CharField(max_length=10, choices=PriceType.choices)
    fiat_currency = models.ForeignKey(FiatCurrency, on_delete=models.PROTECT)
    crypto_currency = models.ForeignKey(CryptoCurrency, on_delete=models.PROTECT)
    fixed_price = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    floating_price = models.DecimalField(max_digits=18, decimal_places=8, default=1)
    trade_floor = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    trade_ceiling = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    trade_limits_in_fiat = models.BooleanField(default=False)
    trade_amount = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    trade_amount_in_fiat = models.BooleanField(default=False)
    appeal_cooldown_choice = models.IntegerField(choices=CooldownChoices.choices, default=CooldownChoices.SIXTY)
    payment_methods = models.ManyToManyField(PaymentMethod, related_name='ads')
    is_public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return str(self.id)

    # modified for soft deletion
    def delete(self):
        self.deleted_at = timezone.now()
        self.save()
    
    @property
    def appeal_cooldown(self):
        # convert to a timedelta object
        minutes = self.appeal_cooldown_choice
        return timedelta(minutes=minutes)

'''A snapshot of the ad is created everytime an order is created.'''
class AdSnapshot(models.Model):
    ad = models.ForeignKey(Ad, on_delete=models.CASCADE, related_name="snapshots")
    trade_type = models.CharField(max_length=4, choices=TradeType.choices, db_index=True)
    price_type = models.CharField(max_length=10, choices=PriceType.choices, db_index=True)
    fiat_currency = models.ForeignKey(FiatCurrency, on_delete=models.PROTECT)
    crypto_currency = models.ForeignKey(CryptoCurrency, on_delete=models.PROTECT)
    fixed_price = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    floating_price = models.DecimalField(max_digits=18, decimal_places=8, default=1)
    market_price = models.DecimalField(max_digits=18, decimal_places=8, default=1)
    trade_floor = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    trade_ceiling = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    trade_limits_in_fiat = models.BooleanField(default=False)
    trade_amount = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    trade_amount_in_fiat = models.BooleanField(default=False)
    appeal_cooldown_choice = models.IntegerField(choices=CooldownChoices.choices)
    payment_types = models.ManyToManyField(PaymentType, related_name='ad_snapshots')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return str(self.id)
    
    @property
    def appeal_cooldown(self):
        # convert to a timedelta object
        minutes = self.appeal_cooldown_choice
        return timedelta(minutes=minutes)