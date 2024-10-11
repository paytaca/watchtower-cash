from rest_framework import serializers

from .models import *
from paytacapos.serializers import MerchantListSerializer


class PaymentVaultSerializer(serializers.ModelSerializer):
    merchant = MerchantListSerializer(many=False)

    class Meta:
        model = PaymentVault
        fields = (
            'user_pubkey',
            'address',
            'token_address',
            'merchant',
        )


class CreatePaymentVaultSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentVault
        fields = (
            'user_pubkey',
            'merchant',
        )