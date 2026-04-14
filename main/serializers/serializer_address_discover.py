from rest_framework import serializers


class AddressDiscoverSetSerializer(serializers.Serializer):
    address_index = serializers.IntegerField()
    receiving = serializers.CharField(max_length=200)
    change = serializers.CharField(max_length=200)


class WalletAddressDiscoverSerializer(serializers.Serializer):
    wallet_hash = serializers.CharField(max_length=200)
    project_id = serializers.CharField(max_length=200, required=False, allow_blank=True)
    address_sets = AddressDiscoverSetSerializer(many=True)


class AddressDiscoverResultSerializer(serializers.Serializer):
    address_index = serializers.IntegerField()
    receiving = serializers.DictField()
    change = serializers.DictField()


class WalletAddressDiscoverResponseSerializer(serializers.Serializer):
    results = AddressDiscoverResultSerializer(many=True)
