from rest_framework import serializers
from django.db.models import Q
from datetime import datetime
from django.utils import timezone
from rampp2p.models import (
    Order,
    CryptoCurrency, 
    FiatCurrency,
    Peer,
    Ad,
    TradeType,
    DurationChoices,
    Status,
    StatusType,
    Arbiter,
    PaymentMethod
)
from .currency import FiatCurrencySerializer, CryptoCurrencySerializer

import logging
logger = logging.getLogger(__name__)

class OrderAdPaymentMethodSerializer(serializers.ModelSerializer):
    payment_type = serializers.SerializerMethodField()
    class Meta:
        model = PaymentMethod
        fields = [
            'payment_type',
            'account_name',
            'account_number'
        ]
    
    def get_payment_type(self, instance: PaymentMethod):
        return instance.payment_type.name

class OrderAdSerializer(serializers.ModelSerializer):
    owner = serializers.SerializerMethodField()
    # payment_methods = OrderAdPaymentMethodSerializer(many=True)
    class Meta:
        model = Ad
        fields = [
            'id',
            'owner'
            # 'payment_methods'
        ]
    
    def get_owner(self, instance: Ad):
        return {
            'id': instance.owner.id,
            'nickname': instance.owner.nickname
        }

class OrderSerializer(serializers.ModelSerializer):
    ad = OrderAdSerializer()
    fiat_currency = FiatCurrencySerializer()
    crypto_currency = CryptoCurrencySerializer()
    arbiter = serializers.SlugRelatedField(slug_field="name", queryset=Peer.objects.all())
    trade_type = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    expiration_date = serializers.SerializerMethodField()
    payment_methods = serializers.SerializerMethodField()
    class Meta:
        model = Order
        fields = [
            'id',
            'ad',
            'crypto_currency',
            'fiat_currency',
            'crypto_amount',
            'locked_price',
            'arbiter',
            'trade_type',
            'status',
            'expiration_date',
            'payment_methods',
            'created_at'
        ]
    
    def get_ad(self, instance: Order):
        data = {
            'id': instance.ad.id,
            'owner': {
                'id': instance.ad.owner.id,
                'nickname': instance.ad.owner.nickname
            }
        }
        return data
    
    def get_payment_methods(self, instance: Order):
        latest_status = self.get_latest_order_status(instance)
        payment_methods = None
        if latest_status.status == StatusType.ESCROWED:
            serialized_payment_methods = OrderAdPaymentMethodSerializer(
                instance.ad.payment_methods.all(), 
                many=True
            )
            payment_methods = serialized_payment_methods.data
        return payment_methods

    def get_latest_order_status(self, instance: Order):
        latest_status = Status.objects.filter(Q(order=instance)).last()
        logger.warn(f'latest_status: {latest_status.status}')
        return latest_status
    
    def get_trade_type(self, instance: Order):
        ad_trade_type = instance.ad.trade_type
        order_trade_type = TradeType.BUY
        if ad_trade_type == TradeType.BUY:
            order_trade_type = TradeType.SELL
        return order_trade_type
    
    def get_status(self, instance: Order):
        latest_status = Status.objects.filter(order__id=instance.id).order_by('-created_at').first().status
        status_type = latest_status
        try:
            status_type = StatusType(latest_status).label
        except ValueError as err:
            logger.error(err)
        
        return status_type
    
    def get_expiration_date(self, instance: Order):
        '''
        Returns the datetime the order expires.
        '''
        time_duration = instance.time_duration
        escrowed_at = Status.objects.values('created_at').filter(Q(order__id=instance.id) & Q(status=StatusType.ESCROWED)).first()
        
        expiration_date = None
        if escrowed_at is not None:
            expiration_date = escrowed_at['created_at'] + time_duration
        
        return expiration_date

class OrderWriteSerializer(serializers.ModelSerializer):
    ad = serializers.PrimaryKeyRelatedField(required=True, queryset=Ad.objects.all())
    owner = serializers.PrimaryKeyRelatedField(required=True, queryset=Peer.objects.all())
    crypto_currency = serializers.PrimaryKeyRelatedField(queryset=CryptoCurrency.objects.all())
    fiat_currency = serializers.PrimaryKeyRelatedField(queryset=FiatCurrency.objects.all())
    arbiter = serializers.PrimaryKeyRelatedField(queryset=Arbiter.objects.all(), required=False)
    locked_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=True)
    crypto_amount = serializers.DecimalField(max_digits=10, decimal_places=8, required=True)
    time_duration_choice = serializers.ChoiceField(choices=DurationChoices.choices,required=True)
    class Meta:
        model = Order
        fields = ['ad', 
                  'owner',
                  'crypto_currency',
                  'fiat_currency',
                  'arbiter',
                  'locked_price',
                  'time_duration_choice',
                  'crypto_amount',
                  'payment_methods']
    
