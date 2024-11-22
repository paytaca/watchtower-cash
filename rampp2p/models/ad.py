from django.db import models
from django.utils import timezone
from django.apps import apps
from rampp2p.utils import satoshi_to_bch, bch_to_fiat
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
    
    trade_floor_sats = models.BigIntegerField(null=True)
    trade_ceiling_sats = models.BigIntegerField(null=True)
    trade_floor = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    trade_ceiling = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    trade_limits_in_fiat = models.BooleanField(default=False)
    
    trade_amount_sats = models.BigIntegerField(null=True)
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

    def get_price(self):
        if self.price_type == PriceType.FIXED:
            return self.fixed_price
        
        MarketRate = apps.get_model('rampp2p', 'MarketRate')
        market_price = MarketRate.objects.filter(currency=self.fiat_currency.symbol).first()
        if market_price:
            market_price = market_price.price
            return market_price * (self.floating_price/100)
        return None
    
    def get_trade_floor(self):
        trade_floor = self.trade_floor_sats

        # convert to satoshi to bch
        trade_floor = satoshi_to_bch(trade_floor)
        
        if self.trade_limits_in_fiat:
            # convert bch to fiat
            ad_price = self.get_price()
            trade_floor = bch_to_fiat(trade_floor, ad_price)
        
        return trade_floor

    def get_trade_ceiling(self):
        trade_ceiling = self.trade_ceiling_sats

        # convert to satoshi to bch
        trade_ceiling = satoshi_to_bch(trade_ceiling)
        
        if self.trade_limits_in_fiat:
            # convert bch to fiat
            ad_price = self.get_price()
            trade_ceiling = bch_to_fiat(trade_ceiling, ad_price)
        
        return trade_ceiling
    
    def get_trade_amount(self):
        trade_amount = self.trade_amount_sats

        # convert to satoshi to bch
        trade_amount = satoshi_to_bch(trade_amount)
        
        if self.trade_amount_in_fiat:
            # convert bch to fiat
            ad_price = self.get_price()
            trade_amount = bch_to_fiat(trade_amount, ad_price)
        
        return trade_amount
        

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
    
    trade_floor_sats = models.BigIntegerField(null=True)
    trade_ceiling_sats = models.BigIntegerField(null=True)
    trade_floor = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    trade_ceiling = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    trade_limits_in_fiat = models.BooleanField(default=False)
    
    trade_amount_sats = models.BigIntegerField(null=True)
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
    
    @property
    def owner(self):
        return self.ad.owner
    
    @property
    def price(self):
        if self.price_type == PriceType.FIXED:
            return self.fixed_price
        return self.market_price * (self.floating_price/100)
    
    def get_trade_floor(self):
        trade_floor = self.trade_floor_sats

        # convert to satoshi to bch
        trade_floor = satoshi_to_bch(trade_floor)
        
        if self.trade_limits_in_fiat:
            # convert bch to fiat
            ad_price = self.get_price()
            trade_floor = bch_to_fiat(trade_floor, ad_price)
        
        return trade_floor

    def get_trade_ceiling(self):
        trade_ceiling = self.trade_ceiling_sats

        # convert to satoshi to bch
        trade_ceiling = satoshi_to_bch(trade_ceiling)
        
        if self.trade_limits_in_fiat:
            # convert bch to fiat
            ad_price = self.get_price()
            trade_ceiling = bch_to_fiat(trade_ceiling, ad_price)
        
        return trade_ceiling
    
    def get_trade_amount(self):
        trade_amount = self.trade_amount_sats

        # convert to satoshi to bch
        trade_amount = satoshi_to_bch(trade_amount)
        
        if self.trade_amount_in_fiat:
            # convert bch to fiat
            ad_price = self.get_price()
            trade_amount = bch_to_fiat(trade_amount, ad_price)
        
        return trade_amount