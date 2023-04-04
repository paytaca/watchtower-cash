from rest_framework import serializers
from ..models.order import Order
from ..models.currency import CryptoCurrency, FiatCurrency
from ..models.peer import Peer
from ..models.payment import PaymentMethod
from ..models.ad import Ad

class OrderSerializer(serializers.ModelSerializer):
  ad = serializers.PrimaryKeyRelatedField(queryset=Ad.objects.all())
  creator = serializers.PrimaryKeyRelatedField(queryset=Peer.objects.all())
  crypto_currency = serializers.PrimaryKeyRelatedField(queryset=CryptoCurrency.objects.all())
  fiat_currency = serializers.PrimaryKeyRelatedField(queryset=FiatCurrency.objects.all())
  arbiter = serializers.PrimaryKeyRelatedField(queryset=Peer.objects.all())
  payment_methods = serializers.PrimaryKeyRelatedField(queryset=PaymentMethod.objects.all(), many=True)
  
  class Meta:
    model = Order
    fields = [
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
    read_only_fields = ["crypto_currency", "fiat_currency", "arbiter", "payment_methods", "chat"]