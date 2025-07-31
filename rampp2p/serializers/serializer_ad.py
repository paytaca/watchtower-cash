from rest_framework import serializers
from rampp2p.utils.fees import get_trading_fees

import rampp2p.models as models
from .serializer_currency import FiatCurrencySerializer, CryptoCurrencySerializer
from .serializer_payment import RelatedPaymentMethodSerializer, PaymentMethodSerializer, SubsetPaymentMethodSerializer

import logging
logger = logging.getLogger(__name__)

class AdSnapshotSerializer(serializers.ModelSerializer):
    """
    Serializer for ad snapshots.

    This serializer handles the serialization of ad snapshot data, providing
    a snapshot of the ad's state at a particular point in time.
    """
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
    """
    Serializer for a subset of ad snapshots.

    This serializer extends the AdSnapshotSerializer and includes additional
    fields specific to the subset of ad snapshots. Overrides the id to return the related Ad id.
    """
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
    
class PublicAdSnapshotSerializer(AdSnapshotSerializer):
    """
    Serializer for public ad snapshots.

    This serializer extends the AdSnapshotSerializer but excludes payment methods
    """

    owner = serializers.SerializerMethodField()

    class Meta(AdSnapshotSerializer.Meta):
        fields = [
            'id',
            'owner',
            'trade_type',
            'price_type',
            'price',
            'market_price',
            'trade_floor',
            'trade_ceiling',
            'trade_amount',
            'trade_limits_in_fiat',
            'payment_types',
            'appeal_cooldown_choice'
        ]
    
    def get_owner(self, obj: models.AdSnapshot):
        return {
            'id': obj.ad.owner.id,
            'name': obj.ad.owner.name
        }
    
class BaseAdSerializer(serializers.ModelSerializer):
    """
    Base serializer for ads.

    This serializer provides the base fields and methods for serializing ad data.
    """
    fiat_currency = FiatCurrencySerializer()
    crypto_currency = CryptoCurrencySerializer()
    appeal_cooldown = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    trade_amount = serializers.SerializerMethodField()
    trade_floor = serializers.SerializerMethodField()
    trade_ceiling = serializers.SerializerMethodField()
    payment_methods = serializers.SerializerMethodField()

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
            'appeal_cooldown'
        ]
    
    def get_appeal_cooldown(self, instance: models.Ad):
        return models.CooldownChoices(instance.appeal_cooldown_choice).value

    def get_price(self, obj: models.Ad):
        return obj.get_price()
    
    def get_trade_amount(self, obj: models.Ad):
        return obj.get_trade_amount()
    
    def get_trade_floor(self, obj: models.Ad):
        return obj.get_trade_floor()
    
    def get_trade_ceiling(self, obj: models.Ad):
        return obj.get_trade_ceiling()
    
    def get_payment_methods(self, obj: models.Ad):
        return obj.payment_methods.values_list('payment_type__short_name', flat=True)

class StoreAdSerializer(BaseAdSerializer):
    """
    Serializer for ads displayed on the P2P exchange's Store page.
    This serializer extends the BaseAdSerializer and adds additional fields
    specific to the Store page.
    """
    
    owner = serializers.SerializerMethodField()
    is_owned = serializers.SerializerMethodField()

    class Meta(BaseAdSerializer.Meta):
        fields = BaseAdSerializer.Meta.fields + [
            'owner',
            'payment_methods',
            'is_owned'
        ]
    
    def get_is_owned(self, obj: models.Ad):
        wallet_hash = self.context.get('wallet_hash')
        if obj.owner.wallet_hash == wallet_hash:
            return True
        return False

    def get_owner(self, obj: models.Ad):
        trade_count = obj.owner.get_trade_count()
        completion_rate = obj.owner.get_completion_rate()
        return {
            'id': obj.owner.id,
            'chat_identity_id': obj.owner.chat_identity_id,
            'name': obj.owner.name,
            'rating':  obj.owner.average_rating(),
            'trade_count': trade_count,
            'completion_rate': completion_rate,
            'is_online': obj.owner.is_online,
            'last_online_at': obj.owner.last_online_at
        }

class ListAdSerializer(BaseAdSerializer):
    """
    Serializer for ads displayed on the P2P exchange's Ads page.
    This serializer extends the BaseAdSerializer and adds additional fields
    specific to the Ads page.
    """

    trade_count = serializers.SerializerMethodField()
    completion_rate = serializers.SerializerMethodField()

    class Meta(BaseAdSerializer.Meta):
        fields = BaseAdSerializer.Meta.fields + [
            'trade_count',
            'completion_rate',
            'payment_methods',
            'is_public'
        ]
    
    def get_trade_count(self, obj: models.Ad):
        return obj.get_trade_count()

    def get_completion_rate(self, obj: models.Ad):
        return obj.get_completion_rate()
    
class CashinAdSerializer(BaseAdSerializer):
    """
    Serializer for ads fetched for the cash-in feature.

    This serializer extends the BaseAdSerializer and adds additional fields
    specific to the cash-in feature.
    """
    
    is_online = serializers.SerializerMethodField()
    last_online_at = serializers.SerializerMethodField()
    payment_methods = RelatedPaymentMethodSerializer(many=True)
    
    class Meta(BaseAdSerializer.Meta):
        fields = BaseAdSerializer.Meta.fields + [
            'payment_methods',
            'is_online',
            'last_online_at'
        ]
    
    def get_is_online(self, obj):
        return obj.owner.is_online

    def get_last_online_at(self, obj):
        return obj.owner.last_online_at

class AdSerializer(BaseAdSerializer):
    """
    Serializer used to serialize more detailed Ad information.
    Extends the BaseAdSerializer.
    """
    owner = serializers.SerializerMethodField()
    fees = serializers.SerializerMethodField()
    is_owned = serializers.SerializerMethodField()
    payment_methods = serializers.SerializerMethodField()

    class Meta(BaseAdSerializer.Meta):
        fields = BaseAdSerializer.Meta.fields + [
            'owner',
            'fees',
            'floating_price',
            'fixed_price',
            'payment_methods',
            'is_owned',
            'is_public'
        ]
    
    def get_payment_methods(self, obj):
        wallet_hash = self.context.get('wallet_hash')
        data = None

        # Return detailed payment method information if user is the ad owner
        if obj.owner.wallet_hash == wallet_hash:
            payment_methods = obj.payment_methods
            data = PaymentMethodSerializer(payment_methods, many=True).data
        else:
            # Return only payment type names if user is not the ad owner
            data = obj.payment_methods.values_list('payment_type__short_name', flat=True)
        return data

    def get_fees(self, _):
        _, fees = get_trading_fees()
        return fees
    
    def get_owner(self, obj: models.Ad):
        return {
            'id': obj.owner.id,
            'chat_identity_id': obj.owner.chat_identity_id,
            'name': obj.owner.name,
            'rating':  obj.owner.average_rating(),
            'is_online': obj.owner.is_online,
            'last_online_at': obj.owner.last_online_at
        }
    
    def get_is_owned(self, obj: models.Ad):
        wallet_hash = self.context.get('wallet_hash')
        if obj.owner.wallet_hash == wallet_hash:
            return True
        return False
   
class WriteAdSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and updating ads.

    This serializer handles the validation and serialization of ad data
    for creating and updating ad instances.
    """
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

    instructions = serializers.CharField(required=False)

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
            'instructions',
            'fiat_currency',
            'crypto_currency',
            'appeal_cooldown_choice',
            'payment_methods',
            'is_public',
            'modified_at'
        ]
