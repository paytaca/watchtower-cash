from rest_framework import serializers

from anyhedge.serializers import PriceOracleMessageSerializer

class FiatTokenPrice(serializers.Serializer):
    category = serializers.CharField()
    currency = serializers.CharField()
    decimals = serializers.IntegerField()
    price_message = PriceOracleMessageSerializer()
