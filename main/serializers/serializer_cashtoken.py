from rest_framework import serializers

from main.models import (
    CashNonFungibleToken,
    CashFungibleToken,
    CashTokenInfo,
)


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
        return obj.info.name

    def get_symbol(self, obj):
        return obj.info.symbol

    def get_decimals(self, obj):
        return obj.info.decimals

    def get_image_url(self, obj):
        return obj.info.image_url
        

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
