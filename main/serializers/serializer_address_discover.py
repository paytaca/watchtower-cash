from rest_framework import serializers


class AddressDiscoverSetSerializer(serializers.Serializer):
    address_index = serializers.IntegerField()
    receiving = serializers.CharField(max_length=200, required=False, allow_blank=True)
    change = serializers.CharField(max_length=200, required=False, allow_blank=True)
    def validate(self, data):
        if not data.get('receiving') and not data.get('change'):
            raise serializers.ValidationError(
                "You must provide at least one of 'receiving' or 'change'."
            )
        return data


class WalletAddressDiscoverSerializer(serializers.Serializer):
    wallet_hash = serializers.CharField(max_length=200)
    project_id = serializers.CharField(max_length=200, required=False, allow_blank=True)
    address_sets = AddressDiscoverSetSerializer(many=True)


class AddressDiscoverResultSerializer(serializers.Serializer):
    address_index = serializers.IntegerField()
    receiving = serializers.DictField(default=dict)
    change = serializers.DictField(default=dict)


class WalletAddressDiscoverResponseSerializer(serializers.Serializer):
    results = AddressDiscoverResultSerializer(many=True)
