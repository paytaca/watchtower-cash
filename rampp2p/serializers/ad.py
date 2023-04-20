from rest_framework import serializers
from ..models.ad import Ad
from ..models.peer import Peer
from ..models.currency import FiatCurrency, CryptoCurrency
from ..models.payment import PaymentMethod

class AdSerializer(serializers.ModelSerializer):
  owner = serializers.PrimaryKeyRelatedField(queryset=Peer.objects.all())
  fiat_currency = serializers.PrimaryKeyRelatedField(queryset=FiatCurrency.objects.all())
  crypto_currency = serializers.PrimaryKeyRelatedField(queryset=CryptoCurrency.objects.all())
  payment_methods = serializers.PrimaryKeyRelatedField(queryset=PaymentMethod.objects.all(), many=True)

  class Meta:
    model = Ad
    fields = [
      "id",
      'owner',
      'trade_type',
      'price_type',
      'fiat_currency',
      'crypto_currency',
      'fixed_price',
      'floating_price',
      'trade_floor',
      'trade_ceiling',
      'crypto_amount',
      'time_limit',
      'payment_methods',
      'modified_at',
    ]
    read_only_fields = [
      'owner',
      'fiat_currency',
      'crypto_currency',
      'payment_methods',
    ]
    depth = 1

class AdWriteSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(queryset=Peer.objects.all())
    fiat_currency = serializers.PrimaryKeyRelatedField(queryset=FiatCurrency.objects.all())
    crypto_currency = serializers.PrimaryKeyRelatedField(queryset=CryptoCurrency.objects.all())
    payment_methods = serializers.PrimaryKeyRelatedField(queryset=PaymentMethod.objects.all(), many=True)

    class Meta:
        model = Ad
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
            'crypto_amount',
            'time_limit',
            'payment_methods',
            'modified_at',
        ]
        read_only_fields = [
        'owner',
        'fiat_currency',
        'crypto_currency',
        'payment_methods',
        ]
        depth = 1