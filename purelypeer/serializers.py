from rest_framework import serializers

from purelypeer.models import Vault


class VaultSerializer(serializers.ModelSerializer):
    class Meta:
        fields = (
            'address',
            'token_address',
            'receiving_pubkey',
            'receiving_pubkey_hash',
        )
