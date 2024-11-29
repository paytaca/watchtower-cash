from rest_framework import serializers
from django.db.models import Q, Subquery, OuterRef
from rampp2p.utils.fees import get_trading_fees

import rampp2p.models as models

from .currency import FiatCurrencySerializer, CryptoCurrencySerializer
from .payment import RelatedPaymentMethodSerializer, PaymentMethodSerializer, SubsetPaymentMethodSerializer

import logging
logger = logging.getLogger(__name__)

class AdSnapshotSerializer(serializers.ModelSerializer):
    price = serializers.SerializerMethodField()
    fiat_currency = FiatCurrencySerializer()
    crypto_currency = CryptoCurrencySerializer()
    trade_floor = serializers.SerializerMethodField()
    trade_ceiling = serializers.SerializerMethodField()
    trade_amount = serializers.SerializerMethodField()
    payment_types = serializers.SlugRelatedField(slug_field="short_name", queryset=models.PaymentType.objects.all(), many=True)
    payment_methods = serializers.SerializerMethodField()
    owner = serializers.SerializerMethodField()

    class Meta:
        model = models.AdSnapshot
        fields = [
            'id',
            'ad',
            'owner',
            'trade_type',
            'price_type',
            'fiat_currency',
            'crypto_currency',
            'floating_price',
            'price',
            'market_price',
            'fixed_price',
            'trade_floor',
            'trade_ceiling',
            'trade_amount',
            'trade_limits_in_fiat',
            'payment_types',
            'payment_methods',
            'appeal_cooldown_choice',
            'created_at'
        ]

    def get_trade_amount(self, obj):
        return obj.get_trade_amount()
    
    def get_trade_floor(self, obj):
        return obj.get_trade_floor()
    
    def get_trade_ceiling(self, obj):
        return obj.get_trade_ceiling()

    def get_price(self, instance: models.AdSnapshot):
        return instance.price
    
    def get_payment_methods(self, obj: models.AdSnapshot):
        payment_type_ids = obj.payment_types.values_list('id')
        payment_types = obj.ad.payment_methods.filter(payment_type__in=payment_type_ids)
        return SubsetPaymentMethodSerializer(payment_types, many=True).data
    
    def get_owner(self, obj: models.AdSnapshot):
        return {
            'id': obj.ad.owner.id,
            'chat_identity_id': obj.ad.owner.chat_identity_id,
            'name': obj.ad.owner.name,
            'rating':  obj.ad.owner.average_rating(),
            'is_online': obj.ad.owner.is_online,
            'last_online_at': obj.ad.owner.last_online_at
        }

class SubsetAdSnapshotSerializer(AdSnapshotSerializer):
    id = serializers.SerializerMethodField()
    owner = serializers.SerializerMethodField()
    fiat_currency = FiatCurrencySerializer()
    crypto_currency = CryptoCurrencySerializer()
    payment_types = serializers.SlugRelatedField(slug_field="short_name", queryset=models.PaymentType.objects.all(), many=True)
    appeal_cooldown = serializers.SerializerMethodField()
    payment_methods = serializers.SerializerMethodField()

    class Meta(AdSnapshotSerializer.Meta):
        fields = [
            'id',
            'owner',
            'payment_types',
            'payment_methods',
            'trade_type',
            'price_type',
            'fiat_currency',
            'crypto_currency',
            'appeal_cooldown',
            'created_at'
        ]
    
    def get_id(self, obj):
        return obj.ad.id

    def get_owner(self, obj):
        return {
            'id': obj.ad.owner.id,
            'name': obj.ad.owner.name
        }
    
    def get_payment_methods(self, obj: models.AdSnapshot):
        payment_type_ids = obj.payment_types.values_list('id')
        payment_types = obj.ad.payment_methods.filter(payment_type__in=payment_type_ids)
        return SubsetPaymentMethodSerializer(payment_types, many=True).data
    
    def get_appeal_cooldown(self, obj):
        return str(obj.appeal_cooldown_choice)

class AdListSerializer(serializers.ModelSerializer):
    owner = serializers.SerializerMethodField()
    fiat_currency = FiatCurrencySerializer()
    crypto_currency = CryptoCurrencySerializer()
    price = serializers.SerializerMethodField()
    
    trade_amount = serializers.SerializerMethodField()
    trade_floor = serializers.SerializerMethodField()
    trade_ceiling = serializers.SerializerMethodField()

    payment_methods = serializers.SerializerMethodField()
    trade_count = serializers.SerializerMethodField()
    completion_rate = serializers.SerializerMethodField()
    is_owned = serializers.SerializerMethodField()
    appeal_cooldown = serializers.SerializerMethodField()

    class Meta:
        model = models.Ad
        fields = [
            'id',
            'owner',
            'trade_type',
            'price_type',
            'fiat_currency',
            'crypto_currency',
            'price',
            'trade_floor',
            'trade_ceiling',
            'trade_amount',
            'trade_limits_in_fiat',
            'trade_amount_in_fiat',
            'payment_methods',
            'trade_count',
            'completion_rate',
            'appeal_cooldown',
            'is_owned',
            'is_public',
            'created_at',
            'modified_at'
        ]

    def get_payment_methods(self, obj: models.Ad):
        return obj.payment_methods.values_list('payment_type__short_name', flat=True)
    
    def get_appeal_cooldown(self, instance: models.Ad):
        return models.CooldownChoices(instance.appeal_cooldown_choice).value
    
    def get_owner(self, obj: models.Ad):
        trade_count = obj.owner.get_trade_count()
        completion_rate = obj.owner.get_completion_rate()
        return {
            'id': obj.owner.id,
            'chat_identity_id': obj.owner.chat_identity_id,
            'name': obj.owner.name,
            'rating':  obj.owner.average_rating(),
            'trade_count': trade_count,
            'completion_rate': completion_rate
        }
    
    def get_is_owned(self, obj: models.Ad):
        wallet_hash = self.context.get('wallet_hash')
        if obj.owner.wallet_hash == wallet_hash:
            return True
        return False
    
    def get_price(self, obj: models.Ad):
        return obj.get_price()
    
    def get_trade_amount(self, obj: models.Ad):
        return obj.get_trade_amount()
    
    def get_trade_floor(self, obj: models.Ad):
        return obj.get_trade_floor()
    
    def get_trade_ceiling(self, obj: models.Ad):
        return obj.get_trade_ceiling()
    
    def get_trade_count(self, obj: models.Ad):
        return obj.get_trade_count()

    def get_completion_rate(self, obj: models.Ad):
        return obj.get_completion_rate()

class CashinAdSerializer(AdListSerializer):
    is_online = serializers.SerializerMethodField()
    last_online_at = serializers.SerializerMethodField()
    payment_methods = RelatedPaymentMethodSerializer(many=True)
    
    class Meta(AdListSerializer.Meta):
        fields = [
            'id',
            'owner',
            'price_type',
            'price',
            'trade_floor',
            'trade_ceiling',
            'trade_amount',
            'trade_limits_in_fiat',
            'trade_amount_in_fiat',
            'payment_methods',
            'trade_count',
            'completion_rate',
            'is_online',
            'last_online_at'
        ]
    
    def get_is_online(self, obj):
        return obj.owner.is_online

    def get_last_online_at(self, obj):
        return obj.owner.last_online_at

class AdDetailSerializer(AdListSerializer):
    fees = serializers.SerializerMethodField()

    class Meta(AdListSerializer.Meta):
        fields = AdListSerializer.Meta.fields + [
            'fees',
            'floating_price',
            'fixed_price',
            'trade_amount'
        ]

    def get_fees(self, _):
        _, fees = get_trading_fees()
        return fees
    
class AdOwnerSerializer(AdDetailSerializer):
    payment_methods = PaymentMethodSerializer(many=True)

    
class AdSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(queryset=models.Peer.objects.all(), required=False)
    trade_type = serializers.ChoiceField(choices=models.TradeType.choices, required=False)
    price_type = serializers.ChoiceField(choices=models.PriceType.choices, required=False)
    fixed_price = serializers.DecimalField(max_digits=18, decimal_places=8, required=False)
    floating_price = serializers.DecimalField(max_digits=18, decimal_places=8, required=False)
    
    trade_floor_sats = serializers.IntegerField(required=False)
    trade_ceiling_sats = serializers.IntegerField(required=False)
    trade_amount_sats = serializers.IntegerField(required=False)

    trade_floor_fiat = serializers.DecimalField(max_digits=18, decimal_places=8, required=False)
    trade_ceiling_fiat = serializers.DecimalField(max_digits=18, decimal_places=8, required=False)
    trade_amount_fiat = serializers.DecimalField(max_digits=18, decimal_places=8, required=False)

    trade_limits_in_fiat = serializers.BooleanField(required=False)
    trade_amount_in_fiat = serializers.BooleanField(required=False)
    fiat_currency = serializers.PrimaryKeyRelatedField(queryset=models.FiatCurrency.objects.all(), required=False)
    crypto_currency = serializers.PrimaryKeyRelatedField(queryset=models.CryptoCurrency.objects.all(), required=False)
    payment_methods = serializers.PrimaryKeyRelatedField(queryset=models.PaymentMethod.objects.all(), many=True, required=False)
    appeal_cooldown_choice = serializers.ChoiceField(choices=models.CooldownChoices.choices, required=False)
    is_public = serializers.BooleanField(required=False)
    modified_at = serializers.DateTimeField(read_only=True)
    
    class Meta:
        model = models.Ad
        fields = [
            'id',
            'owner',
            'trade_type',
            'price_type',
            'fixed_price',
            'floating_price',
            'trade_floor_sats',
            'trade_ceiling_sats',
            'trade_amount_sats',
            'trade_floor_fiat',
            'trade_ceiling_fiat',
            'trade_amount_fiat',
            'trade_limits_in_fiat',
            'trade_amount_in_fiat',
            'fiat_currency',
            'crypto_currency',
            'appeal_cooldown_choice',
            'payment_methods',
            'is_public',
            'modified_at',
        ]
