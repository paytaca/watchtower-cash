from rest_framework import serializers
from rampp2p.models import MarketPrice

class MarketPriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketPrice
        fields = [
            'id',
            'currency',
            'price',
            'modified_at'
        ]