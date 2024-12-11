from rest_framework import serializers

class SignatureData(serializers.Serializer):
    sighash = serializers.CharField(read_only=True)
    signature = serializers.CharField(read_only=True)
    pubkey = serializers.CharField(read_only=True)

class CashscriptTokenNftData(serializers.Serializer):
    capability = serializers.CharField(read_only=True)
    commitment = serializers.CharField(read_only=True)

class CashscriptTokenData(serializers.Serializer):
    category = serializers.CharField(read_only=True)
    amount = serializers.DecimalField(max_digits=20, decimal_places=0, read_only=True)
    nft = CashscriptTokenNftData(read_only=True)

class CashscriptInput(serializers.Serializer):
    txid = serializers.CharField(read_only=True)
    vout = serializers.IntegerField(read_only=True)
    satoshis = serializers.DecimalField(max_digits=20, decimal_places=0, read_only=True)
    token = CashscriptTokenData(read_only=True)

class CashcriptOutput(serializers.Serializer):
    to = serializers.CharField(read_only=True)
    amount = serializers.DecimalField(max_digits=20, decimal_places=0, read_only=True)
    token = CashscriptTokenData(read_only=True)


class TransactionData(serializers.Serializer):
    locktime = serializers.IntegerField(read_only=True)
    inputs = CashscriptInput(many=True, read_only=True)
    outputs = CashcriptOutput(many=True, read_only=True)


class TxidSerializer(serializers.Serializer):
    txid = serializers.CharField(read_only=True)
