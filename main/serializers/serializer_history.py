from rest_framework import serializers

from main.models import WalletHistory

__all__ = [
    "WalletHistoryAttributeSerializer",
    "WalletHistorySerializer",
    "PaginatedWalletHistorySerializer",
]

class WalletHistoryAttributeSerializer(serializers.Serializer):
    wallet_hash = serializers.CharField()
    system_generated = serializers.BooleanField()
    key = serializers.CharField()
    value = serializers.CharField()


class WalletHistorySerializer(serializers.ModelSerializer):
    token = serializers.CharField(read_only=True, source="token__token_id")
    attributes = WalletHistoryAttributeSerializer(many=True, read_only=True)

    class Meta:
        model = WalletHistory
        fields = [
            "record_type",
            "txid",
            "amount",
            "token",
            "tx_fee",
            "senders",
            "recipients",
            "date_created",
            "tx_timestamp",
            "usd_price",
            "attributes",
        ]


class PaginatedWalletHistorySerializer(serializers.Serializer):
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    num_pages = serializers.IntegerField()
    has_next = serializers.BooleanField()    
    history = WalletHistorySerializer(many=True)
