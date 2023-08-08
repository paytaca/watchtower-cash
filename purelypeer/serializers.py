from rest_framework import serializers

from purelypeer.models import Vault
from paytacapos.serializers import MerchantSerializer


class VaultSerializer(serializers.ModelSerializer):
    merchant = MerchantSerializer()
    
    class Meta:
        model = Vault
        fields = (
            'merchant',
            'address',
            'token_address',
            'receiving_pubkey',
            'receiving_pubkey_hash',
        )
