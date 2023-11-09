from rest_framework import serializers
from django.db.models import Q
from rampp2p.models import (
    Order,
    CryptoCurrency, 
    FiatCurrency,
    Peer,
    AdSnapshot,
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
            'id',
            'payment_type',
            'account_name',
            'account_number'
        ]
    
    def get_payment_type(self, instance: PaymentMethod):
        return instance.payment_type.name

class OrderArbiterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Arbiter
        fields = [
            'id',
            'name'
        ]

class OrderSerializer(serializers.ModelSerializer):
    ad = serializers.SerializerMethodField()
    fiat_currency = FiatCurrencySerializer()
    crypto_currency = CryptoCurrencySerializer()
    arbiter = OrderArbiterSerializer()
    trade_type = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    expiration_date = serializers.SerializerMethodField()
    payment_methods = serializers.SerializerMethodField()
    last_modified_at = serializers.SerializerMethodField() # lastest order status created_at
    is_ad_owner = serializers.SerializerMethodField()
    
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
            'created_at',
            'last_modified_at',
            'is_ad_owner'
        ]

    def get_ad(self, instance: Order):
        serialized_payment_methods = OrderAdPaymentMethodSerializer(
            instance.ad_snapshot.payment_methods.all(), 
            many=True
        )
        return {
            'id': instance.ad_snapshot.ad.id,
            'owner': {
                'id': instance.ad_snapshot.ad.owner.id,
                'name': instance.ad_snapshot.ad.owner.name
            },
            'time_duration': instance.ad_snapshot.time_duration_choice,
            'payment_methods': serialized_payment_methods.data
        }
    
    def get_payment_methods(self, instance: Order):
        escrowed_status = Status.objects.filter(Q(order=instance) & Q(status=StatusType.ESCROWED))
        if escrowed_status.exists():            
            serialized_payment_methods = OrderAdPaymentMethodSerializer(
                instance.payment_methods.all(), 
                many=True
            )
            payment_methods = serialized_payment_methods.data
            return payment_methods

    def get_latest_order_status(self, instance: Order):
        latest_status = Status.objects.filter(Q(order=instance)).last()
        return latest_status
    
    def get_trade_type(self, instance: Order):
        ad_trade_type = instance.ad_snapshot.trade_type
        order_trade_type = TradeType.BUY
        if ad_trade_type == TradeType.BUY:
            order_trade_type = TradeType.SELL
        return order_trade_type
    
    def get_status(self, instance: Order):
        latest_status = self.get_latest_order_status(instance)
        if latest_status is not None:
            latest_status = {
                'label': latest_status.get_status_display(),
                'value': latest_status.status
            }
        return latest_status
    
    def get_last_modified_at(self, instance: Order):
        last_modified_at = None
        latest_status = Status.objects.values('created_at').filter(order__id=instance.id).order_by('-created_at').first()
        if latest_status is not None:
            last_modified_at = latest_status['created_at']
        return last_modified_at
    
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
    
    def get_is_ad_owner(self, instance: Order):
        wallet_hash = self.context['wallet_hash']
        if instance.ad_snapshot.ad.owner.wallet_hash == wallet_hash:
            return True
        return False

class OrderWriteSerializer(serializers.ModelSerializer):
    ad_snapshot = serializers.PrimaryKeyRelatedField(required=True, queryset=AdSnapshot.objects.all())
    owner = serializers.PrimaryKeyRelatedField(required=True, queryset=Peer.objects.all())
    crypto_currency = serializers.PrimaryKeyRelatedField(queryset=CryptoCurrency.objects.all())
    fiat_currency = serializers.PrimaryKeyRelatedField(queryset=FiatCurrency.objects.all())
    arbiter = serializers.PrimaryKeyRelatedField(queryset=Arbiter.objects.all(), required=False)
    locked_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=True)
    crypto_amount = serializers.DecimalField(max_digits=10, decimal_places=8, required=True)
    time_duration_choice = serializers.ChoiceField(choices=DurationChoices.choices, required=True)
    payment_methods = serializers.PrimaryKeyRelatedField(queryset=PaymentMethod.objects.all(), required=False, many=True)

    class Meta:
        model = Order
        fields = [
            'ad_snapshot', 
            'owner',
            'crypto_currency',
            'fiat_currency',
            'arbiter',
            'locked_price',
            'time_duration_choice',
            'crypto_amount',
            'payment_methods'
        ]

