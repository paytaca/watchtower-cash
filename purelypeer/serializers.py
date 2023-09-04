from rest_framework import serializers

from purelypeer.models import Vault, Voucher


class VaultSerializer(serializers.ModelSerializer):    
    class Meta:
        model = Vault
        fields = '__all__'


class CreateVoucherSerializer(serializers.ModelSerializer):
    class Meta:
        model = Voucher
        fields = '__all__'


class VoucherClaimCheckSerializer(serializers.Serializer):
    address = serializers.CharField(max_length=100, required=True)  # vault token address
    key_nft_categories = serializers.ListField(
        child=serializers.CharField(max_length=100),
        allow_empty=True
    )


class VoucherClaimCheckResponseSerializer(serializers.Serializer):
    proceed = serializers.BooleanField(default=False)
    expired = serializers.BooleanField(default=False)
    voucher_belongs_to_merchant = serializers.BooleanField(default=False)
    is_merchant_address = serializers.BooleanField(default=False)
    category_with_err = serializers.CharField(max_length=100)
