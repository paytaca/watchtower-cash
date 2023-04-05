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
            'date_created',
            'date_updated',
            'nft_details',
        ]


class CashFungibleTokenSerializer(serializers.ModelSerializer):
    info = CashTokenInfoSerializer()
    
    class Meta:
        model = CashFungibleToken
        fields = [
            'category',
            'info',
        ]


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
