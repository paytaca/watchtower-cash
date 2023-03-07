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
            'is_cashtoken',
            'decimals',
            'token_type',
            'image_url',
            'success',
        ]


class WalletTokenSerializer(serializers.Serializer):
    token_id = serializers.CharField(required=False, allow_blank=True)
    name = serializers.CharField(required=False, allow_blank=True)
    symbol = serializers.CharField(required=False, allow_blank=True)
    type = serializers.IntegerField(required=False)
    nft_token_group = serializers.CharField(required=False)
    original_image_url = serializers.CharField(required=False, allow_blank=True)
    medium_image_url = serializers.CharField(required=False, allow_blank=True)
    thumbnail_image_url = serializers.CharField(required=False, allow_blank=True)
    txid = serializers.CharField(required=False, allow_blank=True)
    date_acquired = serializers.DateTimeField(required=False)
    count = serializers.IntegerField(required=False)
