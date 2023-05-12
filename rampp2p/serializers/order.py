from rest_framework import serializers

from rampp2p.models import (
  Order,
  CryptoCurrency, 
  FiatCurrency,
  Peer,
  Ad
)

class OrderSerializer(serializers.ModelSerializer):
  class Meta:
    model = Order
    fields = [
      'id',
      'ad',
      'owner',
      'crypto_currency',
      'fiat_currency',
      'crypto_amount',
      'locked_price',
      'arbiter',
      'payment_methods'
    ]

class OrderWriteSerializer(serializers.ModelSerializer):
    ad = serializers.PrimaryKeyRelatedField(required=True, queryset=Ad.objects.all())
    owner = serializers.PrimaryKeyRelatedField(required=True, queryset=Peer.objects.all())
    crypto_currency = serializers.PrimaryKeyRelatedField(queryset=CryptoCurrency.objects.all())
    fiat_currency = serializers.PrimaryKeyRelatedField(queryset=FiatCurrency.objects.all())
    arbiter = serializers.PrimaryKeyRelatedField(queryset=Peer.objects.all())
    locked_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=True)
    crypto_amount = serializers.DecimalField(max_digits=10, decimal_places=8, required=True)
    class Meta:
        model = Order
        fields = ['ad', 
                  'owner',
                  'crypto_currency',
                  'fiat_currency',
                  'arbiter',
                  'locked_price',
                  'crypto_amount',
                  'payment_methods']
