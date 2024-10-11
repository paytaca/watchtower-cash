from rest_framework import serializers
from ..models.currency import FiatCurrency, CryptoCurrency

class FiatCurrencySerializer(serializers.ModelSerializer):
  cashin_presets = serializers.SerializerMethodField()
  class Meta:
    model = FiatCurrency
    fields = ['id', 'name', 'symbol', 'cashin_presets']

  def get_cashin_presets(self, obj):
    return obj.get_cashin_presets()
  
class CryptoCurrencySerializer(serializers.ModelSerializer):
  class Meta:
    model = CryptoCurrency
    fields = ['id', 'name', 'symbol']