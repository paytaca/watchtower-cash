from rest_framework import serializers

from main.models import WalletHistory

__all__ = [
    "WalletHistorySerializer",
    "PaginatedWalletHistorySerializer",
]

class WalletHistorySerializer(serializers.ModelSerializer):
    token = serializers.CharField(read_only=True, source="token__token_id")

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
        ]


class PaginatedWalletHistorySerializer(serializers.Serializer):
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    num_pages = serializers.IntegerField()
    has_next = serializers.BooleanField()    
    history = WalletHistorySerializer(many=True)
