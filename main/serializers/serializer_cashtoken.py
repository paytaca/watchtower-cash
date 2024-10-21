from rest_framework import serializers

from django.conf import settings

from main.models import (
    CashNonFungibleToken,
    CashFungibleToken,
    CashTokenInfo,
)

from datetime import timedelta


class CashTokenInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CashTokenInfo
        fields = [
            'name',
            'description',
            'symbol',
            'decimals',
            'image_url',
            'nft_details',
        ]


class CashFungibleTokenSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True, source='token_id')
    name = serializers.SerializerMethodField()
    symbol = serializers.SerializerMethodField()
    decimals = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    
    class Meta:
        model = CashFungibleToken
        fields = [
            'id',
            'name',
            'symbol',
            'decimals',
            'image_url',
        ]

    def get_name(self, obj):
        if obj.info:
            return obj.info.name
        return settings.DEFAULT_TOKEN_DETAILS['fungible']['name']

    def get_symbol(self, obj):
        if obj.info:
            return obj.info.symbol
        return settings.DEFAULT_TOKEN_DETAILS['fungible']['symbol']

    def get_decimals(self, obj):
        if obj.info:
            return obj.info.decimals
        return 0

    def get_image_url(self, obj):
        if obj.info:
            return obj.info.image_url
        return None
            

class CashNonFungibleTokenSerializer(serializers.ModelSerializer):
    info = CashTokenInfoSerializer()
    
    class Meta:
        model = CashNonFungibleToken
        fields = [
            'id',
            'category',
            'commitment',
            'capability',
            'current_txid',
            'current_index',
            'info',
        ]
