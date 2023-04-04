from rest_framework import serializers
from .currency import FiatSerializer, CryptoSerializer
from ..models.ad import Ad

class AdSerializer(serializers.ModelSerializer):
  fiat_currency = FiatSerializer()
  crypto_currency = CryptoSerializer()
  payment_methods = serializers.StringRelatedField(many=True)

  class Meta:
    model = Ad
    fields = [
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