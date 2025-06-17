import logging
from django.db import transaction
from rest_framework import serializers
from ..models.wallet import MultisigWallet, Signer
from ..utils import get_multisig_wallet_locking_script
LOGGER = logging.getLogger(__name__)


class SignerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Signer
        fields = ['entity_key', 'xpub']

class MultisigWalletSerializer(serializers.ModelSerializer):
    signers = SignerSerializer(many=True, read_only=True)
    lockingData = serializers.JSONField(source='locking_data')
    template = serializers.JSONField()

    class Meta:
        model = MultisigWallet
        fields = ['id', 'template', 'lockingData', 'signers', 'created_at', 'locking_bytecode']
        read_only_fields = ['signers', 'created_at']
    
    def create(self, validated_data):
        locking_data = validated_data.get('locking_data', {})
        template = validated_data.get('template', {})
        with transaction.atomic():
            locking_bytecode = get_multisig_wallet_locking_script(template, locking_data)
            wallet, created = MultisigWallet.objects.get_or_create(
                locking_bytecode=locking_bytecode,
                defaults= {
                    'template': template,
                    'locking_data':locking_data,
                    'locking_bytecode':locking_bytecode    
                }
            )
            
            if created:
                hd_public_keys = locking_data.get('hdKeys', {}).get('hdPublicKeys', {})
                for key, value in hd_public_keys.items():
                    Signer.objects.create(
                        wallet=wallet,
                        entity_key=key,
                        xpub=value
                    )
            else:
                if wallet.deleted_at:
                    wallet.deleted_at = None
                    wallet.save(updated_fields=['deleted_at'])
                    
        return wallet
