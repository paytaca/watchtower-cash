from rest_framework import serializers

from smartbch.models import (
    TokenContract,
    Transaction,
    TransactionTransfer,
)


class TokenContractSerializer(serializers.ModelSerializer):
    class Meta:
        model = TokenContract
        fields = (
            "id",
            "address",
            "name",
            "symbol",
            "decimals",
            "image_url",
        )


class TransactionSerializer(serializers.ModelSerializer):
    block_number = serializers.DecimalField(
        source="block.block_number",
        read_only=True,
        max_digits=78,
        decimal_places=0,
    )
    timestamp = serializers.DateTimeField(
        source="block.timestamp",
        read_only=True,
    )
    value = serializers.CharField(source="normalized_value")

    class Meta:
        model = Transaction
        fields = (
            "id",
            "txid",
            "block_number",
            "timestamp",
            "from_addr",
            "to_addr",
            "value",
            "data",
            "gas",
            "gas_used",
            "gas_price",
            "tx_fee",
            "is_mined",
            "status",
        )


class TransactionTransferSerializer(serializers.ModelSerializer):
    txid = serializers.CharField(source="transaction.txid", read_only=True)
    block_number = serializers.DecimalField(
        source="transaction.block.block_number",
        read_only=True,
        max_digits=78,
        decimal_places=0,
    )
    timestamp = serializers.DateTimeField(
        source="transaction.block.timestamp",
        read_only=True,
    )
    token_contract = TokenContractSerializer(read_only=True)
    tx_fee = serializers.FloatField(source="transaction.tx_fee", read_only=True)
    amount = serializers.CharField(source="normalized_amount")

    class Meta:
        model = TransactionTransfer
        fields = (
            "id",
            "txid",
            "block_number",
            "timestamp",
            "token_contract",
            "log_index",
            "from_addr",
            "to_addr",
            "amount",
            "token_id",
            "tx_fee",
        )
