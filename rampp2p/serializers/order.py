from rest_framework import serializers
from django.db.models import Q
import rampp2p.models as models
from .currency import FiatCurrencySerializer, CryptoCurrencySerializer

import logging
logger = logging.getLogger(__name__)

class OrderMemberSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    chat_identity_id = serializers.IntegerField()
    public_key = serializers.CharField()
    name = serializers.CharField()
    address = serializers.CharField()
    is_arbiter = serializers.BooleanField()

class OrderAdPaymentMethodSerializer(serializers.ModelSerializer):
    payment_type = serializers.SerializerMethodField()
    class Meta:
        model = models.PaymentMethod
        fields = [
            'id',
            'payment_type',
            'account_name',
            'account_identifier'
        ]
    
    def get_payment_type(self, obj):
        return obj.payment_type.name

class OrderArbiterSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Arbiter
        fields = [
            'id',
            'name'
        ]

class OrderSerializer(serializers.ModelSerializer):
    ad = serializers.SerializerMethodField()
    owner = serializers.SerializerMethodField()
    contract  = serializers.SerializerMethodField()
    fiat_currency = FiatCurrencySerializer()
    crypto_currency = CryptoCurrencySerializer()
    arbiter = OrderArbiterSerializer()
    trade_type = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    payment_methods = serializers.SerializerMethodField()
    last_modified_at = serializers.SerializerMethodField() # lastest order status created_at
    is_ad_owner = serializers.SerializerMethodField()
    
    class Meta:
        model = models.Order
        fields = [
            'id',
            'ad',
            'owner',
            'contract',
            'crypto_currency',
            'fiat_currency',
            'crypto_amount',
            'locked_price',
            'arbiter',
            'trade_type',
            'status',
            'payment_methods',
            'created_at',
            'expires_at',
            'last_modified_at',
            'is_ad_owner'
        ]

    def get_ad(self, obj):
        serialized_payment_methods = OrderAdPaymentMethodSerializer(
            obj.ad_snapshot.payment_methods.all(), 
            many=True
        )
        return {
            'id': obj.ad_snapshot.ad.id,
            'owner': {
                'id': obj.ad_snapshot.ad.owner.id,
                'name': obj.ad_snapshot.ad.owner.name
            },
            'time_duration': obj.ad_snapshot.time_duration_choice,
            'payment_methods': serialized_payment_methods.data
        }
    
    def get_owner(self, obj):
        return {
            'id': obj.id,
            'name': obj.owner.name,
            'rating': obj.owner.average_rating()
        }

    def get_contract(self, obj):
        try:
            contract = models.Contract.objects.get(order=obj)
        except models.Contract.DoesNotExist:
            return None
        return contract.id

    def get_payment_methods(self, obj):
        escrowed_status = models.Status.objects.filter(Q(order=obj) & Q(status=models.StatusType.ESCROWED))
        if escrowed_status.exists():            
            serialized_payment_methods = OrderAdPaymentMethodSerializer(
                obj.payment_methods.all(), 
                many=True
            )
            payment_methods = serialized_payment_methods.data
            return payment_methods

    def get_latest_order_status(self, obj):
        latest_status = models.Status.objects.filter(Q(order=obj)).last()
        return latest_status
    
    def get_trade_type(self, obj):
        ad_trade_type = obj.ad_snapshot.trade_type
        order_trade_type = models.TradeType.BUY
        if ad_trade_type == models.TradeType.BUY:
            order_trade_type = models.TradeType.SELL
        return order_trade_type
    
    def get_status(self, obj):
        latest_status = self.get_latest_order_status(obj)
        if latest_status is not None:
            latest_status = {
                'label': latest_status.get_status_display(),
                'value': latest_status.status
            }
        return latest_status
    
    def get_last_modified_at(self, obj):
        last_modified_at = None
        latest_status = models.Status.objects.values('created_at').filter(order__id=obj.id).order_by('-created_at').first()
        if latest_status is not None:
            last_modified_at = latest_status['created_at']
        return last_modified_at
    
    def get_is_ad_owner(self, obj):
        wallet_hash = self.context['wallet_hash']
        if obj.ad_snapshot.ad.owner.wallet_hash == wallet_hash:
            return True
        return False

class OrderWriteSerializer(serializers.ModelSerializer):
    ad_snapshot = serializers.PrimaryKeyRelatedField(required=True, queryset=models.AdSnapshot.objects.all())
    owner = serializers.PrimaryKeyRelatedField(required=True, queryset=models.Peer.objects.all())
    crypto_currency = serializers.PrimaryKeyRelatedField(queryset=models.CryptoCurrency.objects.all())
    fiat_currency = serializers.PrimaryKeyRelatedField(queryset=models.FiatCurrency.objects.all())
    arbiter = serializers.PrimaryKeyRelatedField(queryset=models.Arbiter.objects.all(), required=False)
    locked_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=True)
    crypto_amount = serializers.DecimalField(max_digits=10, decimal_places=8, required=True)
    time_duration_choice = serializers.ChoiceField(choices=models.DurationChoices.choices, required=True)
    payment_methods = serializers.PrimaryKeyRelatedField(queryset=models.PaymentMethod.objects.all(), required=False, many=True)

    class Meta:
        model = models.Order
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

