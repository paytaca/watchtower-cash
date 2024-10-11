from rest_framework import serializers

class WalletAddressesSerializer(serializers.Serializer):
    wallet_hash = serializers.CharField(required=True)