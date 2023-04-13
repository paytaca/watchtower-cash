from rest_framework import serializers
from ..models.order import Order
from ..models.currency import CryptoCurrency, FiatCurrency
from ..models.peer import Peer
from ..models.payment import PaymentMethod
from ..models.ad import Ad

class OrderSerializer(serializers.ModelSerializer):
  # ad = serializers.PrimaryKeyRelatedField(queryset=Ad.objects.all())
  # creator = serializers.PrimaryKeyRelatedField(queryset=Peer.objects.all())
  # crypto_currency = serializers.PrimaryKeyRelatedField(queryset=CryptoCurrency.objects.all())
  # fiat_currency = serializers.PrimaryKeyRelatedField(queryset=FiatCurrency.objects.all())
  # arbiter = serializers.PrimaryKeyRelatedField(queryset=Peer.objects.all())
  # payment_methods = serializers.PrimaryKeyRelatedField(queryset=PaymentMethod.objects.all(), many=True)
  
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
    read_only_fields = ["crypto_currency", "fiat_currency", "arbiter", "payment_methods"]
    depth = 1

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

    # def create(self, validated_data):
    #   # TODO: set the creator of the order based on the submitted wallethash
    #   payment_methods = validated_data.pop('payment_methods')
    #   order = Order(
    #     ad=validated_data['ad'],
    #     creator=validated_data['creator'],
    #     crypto_currency=validated_data['ad'].crypto_currency,
    #     fiat_currency=validated_data['ad'].fiat_currency,
    #     fiat_amount=validated_data['fiat_amount'],
    #     locked_price=validated_data['locked_price'],
    #     arbiter=validated_data['arbiter'],
    #   )
    #   order.payment_methods.add(*payment_methods)

    #   return Order.objects.create(**validated_data)

