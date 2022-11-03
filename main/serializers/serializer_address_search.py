from rest_framework import serializers


class AddressSetSerializer(serializers.Serializer):
    change = serializers.CharField(max_length=200)
    receiving = serializers.CharField(max_length=200)


class WalletAddressSetSerializer(serializers.Serializer):
    address_index = serializers.IntegerField()
    addresses = AddressSetSerializer()


class WalletAddressSearchSerializer(serializers.Serializer):
    wallet_hash = serializers.CharField(max_length=200)
    project_id = serializers.CharField(max_length=200, required=False, allow_blank=True)
    address_sets = WalletAddressSetSerializer(many=True)
