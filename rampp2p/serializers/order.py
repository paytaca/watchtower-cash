from rest_framework import serializers

from ..base_models import (
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
      "id",
      "ad",
      "creator",
      "crypto_currency",
      "fiat_currency",
      "fiat_amount",
      "locked_price",
      "arbiter",
      "contract_address",
      "payment_methods",
      "is_appealed"
    ]

class OrderWriteSerializer(serializers.ModelSerializer):
  ad = serializers.PrimaryKeyRelatedField(required=True, queryset=Ad.objects.all())
  creator = serializers.PrimaryKeyRelatedField(required=True, queryset=Peer.objects.all())
  crypto_currency = serializers.PrimaryKeyRelatedField(queryset=CryptoCurrency.objects.all())
  fiat_currency = serializers.PrimaryKeyRelatedField(queryset=FiatCurrency.objects.all())

  class Meta:
    model = Order
    fields = [
      'ad',
      'creator',
      "crypto_currency",
      "fiat_currency",
      'fiat_amount',
      'locked_price',
      'arbiter',
      'payment_methods'
    ]