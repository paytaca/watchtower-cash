from rest_framework import serializers
from ..models.currency import FiatCurrency, CryptoCurrency

class FiatSerializer(serializers.ModelSerializer):
  class Meta:
    model = FiatCurrency
    fields = ['id', 'name', 'abbrev']
  
class CryptoSerializer(serializers.ModelSerializer):
  class Meta:
    model = CryptoCurrency
    fields = ['id', 'name', 'abbrev']