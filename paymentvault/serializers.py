from rest_framework import serializers

from .models import *
from .utils import get_payment_vault
from paytacapos.serializers import MerchantListSerializer


class PaymentVaultSerializer(serializers.ModelSerializer):
    merchant = MerchantListSerializer(many=False)
    balance = serializers.SerializerMethodField()

    class Meta:
        model = PaymentVault
        fields = (
            'user_pubkey',
            'address',
            'token_address',
            'merchant',
            'balance',
        )

    def get_balance(self, obj):
        try:
            vault = get_payment_vault(obj.user_pubkey, obj.merchant.pubkey)
            return vault['balance']
        except:
            return 0


class CreatePaymentVaultSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentVault
        fields = (
            'user_pubkey',
            'merchant',
        )