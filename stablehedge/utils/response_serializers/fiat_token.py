from rest_framework import serializers

class FiatTokenPrice(serializers.Serializer):
    category = serializers.CharField()
    price = serializers.IntegerField()
    currency = serializers.CharField()
    decimals = serializers.IntegerField()
    timestamp = serializers.DateTimeField()
