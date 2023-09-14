from rest_framework import serializers

from datetime import timedelta

from vouchers.models import *


class VaultSerializer(serializers.ModelSerializer):    
    class Meta:
        model = Vault
        fields = '__all__'


class VoucherSerializer(serializers.ModelSerializer):    
    class Meta:
        model = Voucher
        fields = (
            'vault',
            'value',
            'minting_txid',
            'claim_txid',
            'key_category',
            'lock_category',
            'claimed',
            'expired',
            'duration_days',
            'date_created',
            'date_claimed',
            'expiration_date',
        )

        read_only_fields = (
            'expiration_date',
            'id',
        )


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


class VoucherClaimedResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(default=False)


class VoucherClaimedSerializer(serializers.Serializer):
    lock_category = serializers.CharField(max_length=100, required=True)
    txid = serializers.CharField(max_length=100, required=True)
