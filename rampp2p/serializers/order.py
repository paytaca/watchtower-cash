from rest_framework import serializers
from rampp2p.models import (
    Order,
    CryptoCurrency, 
    FiatCurrency,
    Peer,
    Ad,
    DurationChoices
)
from .currency import FiatCurrencySerializer, CryptoCurrencySerializer
from .payment import RelatedPaymentMethodSerializer

class OrderSerializer(serializers.ModelSerializer):
    ad_owner_name = serializers.SerializerMethodField()
    fiat_currency = FiatCurrencySerializer()
    crypto_currency = CryptoCurrencySerializer()
    arbiter = serializers.SlugRelatedField(slug_field="nickname", queryset=Peer.objects.all())
    trade_type = serializers.SerializerMethodField()
    # payment_methods = RelatedPaymentMethodSerializer(many=True)
    class Meta:
        model = Order
        fields = [
            'id',
            'ad_owner_name',
            'crypto_currency',
            'fiat_currency',
            'crypto_amount',
            'time_duration_choice',
            'locked_price',
            'arbiter',
            'trade_type',
            # 'payment_methods'
        ]
    
    def get_ad_owner_name(self, instance: Order):
        return instance.ad.owner.nickname
    
    def get_trade_type(self, instance: Order):
        return instance.ad.trade_type


class OrderWriteSerializer(serializers.ModelSerializer):
    ad = serializers.PrimaryKeyRelatedField(required=True, queryset=Ad.objects.all())
    owner = serializers.PrimaryKeyRelatedField(required=True, queryset=Peer.objects.all())
    crypto_currency = serializers.PrimaryKeyRelatedField(queryset=CryptoCurrency.objects.all())
    fiat_currency = serializers.PrimaryKeyRelatedField(queryset=FiatCurrency.objects.all())
    arbiter = serializers.PrimaryKeyRelatedField(queryset=Peer.objects.all())
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
