from rest_framework import serializers
from main.utils.address_scan import sort_address_sets


class AddressSetSerializer(serializers.Serializer):
    change = serializers.CharField(max_length=200)
    receiving = serializers.CharField(max_length=200)


class WalletAddressSetSerializer(serializers.Serializer):
    address_index = serializers.IntegerField()
    addresses = AddressSetSerializer()


class WalletAddressScanSerializer(serializers.Serializer):
    wallet_hash = serializers.CharField(max_length=200)
    project_id = serializers.CharField(max_length=200, required=False, allow_blank=True)
    address_sets = WalletAddressSetSerializer(many=True)

    def sorted_address_sets(self):
        address_sets = self.validated_data["address_sets"]
        return sort_address_sets(address_sets)


class WalletAddressScanResponseSerializer(serializers.Serializer):
    address_set = WalletAddressSetSerializer()
    success = serializers.BooleanField()
    error = serializers.CharField(required=False, allow_blank=True)
