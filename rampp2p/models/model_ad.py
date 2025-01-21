from django.db import models
from django.utils import timezone
from django.apps import apps

from rampp2p.utils import satoshi_to_bch
from datetime import timedelta

from .model_peer import Peer
from .model_currency import FiatCurrency, CryptoCurrency
from .model_payment import PaymentMethod, PaymentType

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
    
    trade_floor_fiat = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    trade_ceiling_fiat = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    trade_amount_fiat = models.DecimalField(max_digits=18, decimal_places=2, default=0)
   
    trade_floor_sats = models.BigIntegerField(null=True)
    trade_ceiling_sats = models.BigIntegerField(null=True)
    trade_amount_sats = models.BigIntegerField(null=True)
   
    trade_limits_in_fiat = models.BooleanField(default=False)

    ### retained for legacy support
    trade_floor = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    trade_ceiling = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    trade_amount = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    trade_amount_in_fiat = models.BooleanField(default=False)
    ### retained for legacy support

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
        
        MarketPrice = apps.get_model('rampp2p', 'MarketPrice')
        market_price = MarketPrice.objects.filter(currency=self.fiat_currency.symbol).first()
        if market_price:
            market_price = market_price.price
            return market_price * (self.floating_price/100)
        return None
    
    def get_trade_floor(self):
        if self.trade_limits_in_fiat:
            return self.trade_floor_fiat
        
        trade_floor = self.trade_floor_sats
        trade_floor = satoshi_to_bch(trade_floor)
        
        return trade_floor

    def get_trade_ceiling(self):
        if self.trade_limits_in_fiat:
            return self.trade_ceiling_fiat
        
        trade_ceiling = self.trade_ceiling_sats
        trade_ceiling = satoshi_to_bch(trade_ceiling)
        
        return trade_ceiling
    
    def get_trade_amount(self):
        if self.trade_limits_in_fiat:
            return self.trade_amount_fiat
        
        trade_amount = self.trade_amount_sats
        trade_amount = satoshi_to_bch(trade_amount)
        
        return trade_amount
    
    def get_trade_count(self):
        Order = apps.get_model('rampp2p', 'Order')
        return Order.objects.filter(ad_snapshot__ad__id=self.id).count()
    
    def count_orders_by_status(self, status: str):
        Status = apps.get_model('rampp2p', 'Status')
        latest_status_subquery = Status.objects.filter(order_id=models.OuterRef('id')).order_by('-created_at').values('status')[:1]
       
        Order = apps.get_model('rampp2p', 'Order')
        user_orders = Order.objects.filter(models.Q(ad_snapshot__ad__id=self.id)).annotate(
            latest_status = models.Subquery(latest_status_subquery)
        )

        return user_orders.filter(status__status=status).count()
    
    def count_completed_orders(self):
        completed_statuses = ['RLS', 'CNCL', 'RFN']
        total_count = 0
        for status in completed_statuses:
            total_count += self.count_orders_by_status(status)

        return total_count
    
    def count_released_orders(self):
        return self.count_orders_by_status('RLS')
    
    def get_completion_rate(self):
        # completion_rate = released_count / (released_count + canceled_count + refunded_count)
        completed_count = self.count_completed_orders()
        released_count = self.count_released_orders()
        completion_rate = 0
        if completed_count > 0:
            completion_rate = released_count / completed_count * 100
        return completion_rate
        

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
    
    trade_floor_fiat = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    trade_ceiling_fiat = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    
    trade_floor_sats = models.BigIntegerField(null=True)
    trade_ceiling_sats = models.BigIntegerField(null=True)
    
    trade_floor = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    trade_ceiling = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    trade_limits_in_fiat = models.BooleanField(default=False)

    trade_amount_fiat = models.DecimalField(max_digits=18, decimal_places=2, default=0)
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
        trade_floor = self.trade_floor
        
        if self.trade_limits_in_fiat:
            trade_floor = self.trade_floor_fiat
        else:
            trade_floor = self.trade_floor_sats
            trade_floor = satoshi_to_bch(trade_floor)        
        return trade_floor

    def get_trade_ceiling(self):
        trade_ceiling = self.trade_ceiling

        if self.trade_limits_in_fiat:
            trade_ceiling = self.trade_ceiling_fiat
        else:
            trade_ceiling = self.trade_ceiling_sats
            trade_ceiling = satoshi_to_bch(trade_ceiling)
        
        return trade_ceiling
    
    def get_trade_amount(self):
        trade_amount = self.trade_amount

        if self.trade_limits_in_fiat:
            trade_amount = self.trade_amount_fiat
        else:
            trade_amount = self.trade_amount_sats
            trade_amount = satoshi_to_bch(trade_amount)
        
        return trade_amount