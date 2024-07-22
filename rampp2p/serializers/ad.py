from rest_framework import serializers
from rampp2p.utils.utils import get_trading_fees
from django.db.models import Q, Subquery, OuterRef, F
import rampp2p.models as models
from .currency import FiatCurrencySerializer, CryptoCurrencySerializer
from .payment import RelatedPaymentMethodSerializer, PaymentMethodSerializer, SubsetPaymentMethodSerializer

class AdSnapshotSerializer(serializers.ModelSerializer):
    price = serializers.SerializerMethodField()
    fiat_currency = FiatCurrencySerializer()
    crypto_currency = CryptoCurrencySerializer()
    payment_types = serializers.SlugRelatedField(slug_field="short_name", queryset=models.PaymentType.objects.all(), many=True)
    payment_methods = serializers.SerializerMethodField()

    class Meta:
        model = models.AdSnapshot
        fields = [
            'id',
            'ad',
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
            'trade_limits_in_fiat',
            'trade_amount',
            'trade_amount_in_fiat',
            'payment_types',
            'payment_methods',
            'appeal_cooldown_choice',
            'created_at'
        ]

    def get_price(self, instance: models.AdSnapshot):
        if instance.price_type == models.PriceType.FIXED:
            return instance.fixed_price
        return instance.market_price * (instance.floating_price/100)
    
    def get_payment_methods(self, obj: models.AdSnapshot):
        payment_type_ids = obj.payment_types.values_list('id')
        payment_types = obj.ad.payment_methods.filter(payment_type__in=payment_type_ids)
        return SubsetPaymentMethodSerializer(payment_types, many=True).data

class SubsetAdSnapshotSerializer(AdSnapshotSerializer):
    id = serializers.SerializerMethodField()
    fiat_currency = FiatCurrencySerializer()
    crypto_currency = CryptoCurrencySerializer()
    payment_types = serializers.SlugRelatedField(slug_field="short_name", queryset=models.PaymentType.objects.all(), many=True)
    appeal_cooldown = serializers.SerializerMethodField()
    payment_methods = serializers.SerializerMethodField()

    class Meta(AdSnapshotSerializer.Meta):
        fields = [
            'id',
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
    # payment_methods = RelatedPaymentMethodSerializer(many=True)
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
    
    def get_owner(self, instance: models.Ad):
        return {
            'id': instance.owner.id,
            'name': instance.owner.name,
            'rating':  instance.owner.average_rating()
        }
    
    def get_is_owned(self, instance: models.Ad):
        wallet_hash = ''
        try:
            wallet_hash = self.context['wallet_hash']
        except KeyError:
            pass
        if instance.owner.wallet_hash == wallet_hash:
            return True
        return False
    
    def get_price(self, instance: models.Ad):
        if instance.price_type == models.PriceType.FIXED:
            return instance.fixed_price
        
        currency = instance.fiat_currency.symbol
        market_price = models.MarketRate.objects.filter(currency=currency)
        if market_price.exists():
            market_price = market_price.first().price
            price = market_price * (instance.floating_price/100)
        else:
            price = None
        return price
    
    def get_trade_count(self, instance: models.Ad):
        return models.Order.objects.filter(Q(ad_snapshot__ad__id=instance.id)).count()

    def get_completion_rate(self, instance: models.Ad):
        ''' 
        completion_rate = released_count / (released_count + canceled_count + refunded_count)
        '''
        released_count, completed_count = self.get_completed_orders_count(instance.id)
        completion_rate = 0
        if completed_count > 0:
            completion_rate = released_count / completed_count * 100
        return completion_rate
    
    def get_completed_orders_count(self, ad_id: int):
        # Subquery to get the latest status for each order
        latest_status_subquery = models.Status.objects.filter(order_id=OuterRef('id')).order_by('-created_at').values('status')[:1]
        
        user_orders = models.Order.objects.filter(Q(ad_snapshot__ad__id=ad_id)).annotate(
            latest_status = Subquery(latest_status_subquery)
        )

        completed_statuses = [models.StatusType.RELEASED.value, models.StatusType.CANCELED.value, models.StatusType.REFUNDED.value]
        completed_orders_count = user_orders.filter(status__status__in=completed_statuses).count()
        release_orders_count = user_orders.filter(status__status=models.StatusType.RELEASED).count()
        return release_orders_count, completed_orders_count

class CashinAdSerializer(AdListSerializer):
    is_online = serializers.SerializerMethodField()
    last_online_at = serializers.SerializerMethodField()

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

class AdCreateSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(queryset=models.Peer.objects.all())
    fiat_currency = serializers.PrimaryKeyRelatedField(queryset=models.FiatCurrency.objects.all())
    crypto_currency = serializers.PrimaryKeyRelatedField(queryset=models.CryptoCurrency.objects.all())
    payment_methods = serializers.PrimaryKeyRelatedField(queryset=models.PaymentMethod.objects.all(), many=True)
    appeal_cooldown_choice = serializers.ChoiceField(choices=models.CooldownChoices.choices,required=True)
    class Meta:
        model = models.Ad
        fields = [
            'id',
            'owner',
            'trade_type',
            'price_type',
            'fiat_currency',
            'crypto_currency',
            'fixed_price',
            'floating_price',
            'trade_floor',
            'trade_ceiling',
            'trade_amount',
            'trade_limits_in_fiat',
            'trade_amount_in_fiat',
            'appeal_cooldown_choice',
            'payment_methods',
            'is_public',
            'modified_at',
        ]
    
class AdUpdateSerializer(serializers.ModelSerializer):
    payment_methods = serializers.PrimaryKeyRelatedField(queryset=models.PaymentMethod.objects.all(), many=True)
    appeal_cooldown_choice = serializers.ChoiceField(choices=models.CooldownChoices.choices)
    class Meta:
        model = models.Ad
        fields = [
            'price_type',
            'fixed_price',
            'floating_price',
            'trade_floor',
            'trade_ceiling',
            'trade_amount',
            'trade_limits_in_fiat',
            'trade_amount_in_fiat',
            'fiat_currency',
            'appeal_cooldown_choice',
            'payment_methods',
            'is_public',
            'modified_at',
        ]