from rest_framework import serializers

from datetime import timedelta

from main.serializers import CashNonFungibleTokenSerializer
from vouchers.models import *


class PosDeviceVaultSerializer(serializers.ModelSerializer):
    category = serializers.SerializerMethodField()

    class Meta:
        model = PosDeviceVault
        fields = (
            'id',
            'pos_device',
            'address',
            'token_address',
            'pubkey',
            'category',
        )
    
    def get_category(self, obj):
        try:
            return obj.pos_device.merchant.minter.category
        except:
            return None


class MerchantVaultSerializer(serializers.ModelSerializer):    
    class Meta:
        model = MerchantVault
        fields = '__all__'


class VerificationTokenMinterSerializer(serializers.ModelSerializer):    
    class Meta:
        model = VerificationTokenMinter
        fields = '__all__'


class LatestPosIdSerializer(serializers.Serializer):
    wallet_hash = serializers.CharField()


class LatestPosIdResponseSerializer(serializers.Serializer):
    posid = serializers.IntegerField()


class VoucherSerializer(serializers.ModelSerializer):
    capability = serializers.SerializerMethodField()
    merchant = serializers.SerializerMethodField()
    nft = CashNonFungibleTokenSerializer()

    class Meta:
        model = Voucher
        fields = (
            'id',
            'vault',
            'merchant',
            'nft',
            'value',
            'minting_txid',
            'claim_txid',
            'category',
            'commitment',
            'capability',
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
            'capability',
        )

    def get_capability(self, obj):
        return 'none'
    
    def get_merchant(self, obj):
        return obj.vault.merchant.name


class VoucherClaimVerificationSerializer(serializers.Serializer):
    device_vault_token_address = serializers.CharField(max_length=100, required=True)
    voucher_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=True
    )


class VoucherClaimCheckResponseSerializer(serializers.Serializer):
    proceed = serializers.BooleanField(default=False)
    voucher_id = serializers.JSONField()


class VoucherClaimedResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(default=False)