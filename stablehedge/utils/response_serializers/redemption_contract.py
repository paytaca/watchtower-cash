from rest_framework import serializers

from .common import CommonResponseSerializer


class RedemptionContractTransactionMeta(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    redemption_contract = serializers.CharField(read_only=True)
    transaction_type = serializers.CharField(read_only=True)
    price = serializers.FloatField(read_only=True)
    currency = serializers.CharField(read_only=True)
    satoshis = serializers.IntegerField(read_only=True)
    amount = serializers.FloatField(read_only=True)


class RedemptionContractTransactionMetaResponse(CommonResponseSerializer):
    txid = serializers.CharField(read_only=True)
    data = RedemptionContractTransactionMeta(read_only=True)


class RedemptionContractWalletBalance(serializers.Serializer):
    category = serializers.CharField(read_only=True)
    total_amount = serializers.IntegerField(read_only=True)
    current_price = serializers.IntegerField(read_only=True)
    redeemable_satoshis = serializers.IntegerField(read_only=True)
