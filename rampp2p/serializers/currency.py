from rest_framework import serializers
from ..models.currency import FiatCurrency, CryptoCurrency

class FiatCurrencySerializer(serializers.ModelSerializer):
  class Meta:
    model = FiatCurrency
    fields = ['id', 'name', 'symbol']
  
class CryptoCurrencySerializer(serializers.ModelSerializer):
  class Meta:
    model = CryptoCurrency
    fields = ['id', 'name', 'symbol']