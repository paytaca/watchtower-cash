from main.models import Token
from rest_framework import serializers, exceptions

class TokenSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True, source="info_id")
    image_url = serializers.CharField(read_only=True)
    symbol = serializers.CharField(read_only=True, source="token_ticker")

    success = serializers.BooleanField(read_only=True)

    class Meta:
        model = Token
        fields = [
            'id',
            'name',
            'symbol',
            'decimals',
            'token_type',
            'image_url',
            'success',
        ]
