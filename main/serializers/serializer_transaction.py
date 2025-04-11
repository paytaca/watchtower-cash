from rest_framework import serializers

from main import models

class TransactionOutputSerializer(serializers.ModelSerializer):
    address = serializers.CharField(source="address.address", read_only=True)
    block = serializers.IntegerField(source="blockheight.number", read_only=True)
    category = serializers.CharField()
    capability = serializers.CharField(source="cashtoken_nft.capability", read_only=True)
    commitment = serializers.CharField(source="cashtoken_nft.commitment", read_only=True)
    token_ticker = serializers.CharField(read_only=True)
    decimals = serializers.IntegerField(read_only=True)
 
    class Meta:
        model = models.Transaction
        fields = [
            "block",
            "txid",
            "index",
            "value",
            "address",
            "category",
            "amount",
            "capability",
            "commitment",
            "token_ticker",
            "decimals",
            "spent",
            "spending_txid",
            "tx_timestamp",
        ]