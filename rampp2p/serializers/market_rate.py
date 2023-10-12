from rest_framework import serializers
from rampp2p.models import MarketRate

class MarketRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketRate
        fields = [
            'id',
            'currency',
            'price',
            'modified_at'
        ]