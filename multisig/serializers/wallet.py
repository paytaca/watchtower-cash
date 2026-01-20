import logging
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from ..models.wallet import MultisigWallet, Signer
from django.db import transaction
LOGGER = logging.getLogger(__name__)

class SignerSerializer(serializers.ModelSerializer):
    # Map camelCase client fields to snake_case model fields
    pubkeyZero = serializers.CharField(source='pubkey_zero')
    walletBsmsDescriptor = serializers.CharField(source='wallet_bsms_descriptor')
    derivationPath = serializers.CharField(source='derivation_path', required=False, allow_blank=True)
    masterFingerprint = serializers.CharField(source='master_fingerprint', required=False, allow_blank=True)

    class Meta:
        model = Signer
        fields = ['id', 'name', 'pubkeyZero', 'walletBsmsDescriptor', 'derivationPath', 'masterFingerprint']
        read_only_fields = ['id']


class MultisigWalletSerializer(serializers.ModelSerializer):
    # Map camelCase client fields to snake_case model fields
    walletHash = serializers.CharField(source='wallet_hash')
    walletName = serializers.CharField(source='name')
    # Accept but don't store this field (not in model)
    walletDescription = serializers.CharField(write_only=True, required=False, allow_blank=True)
    signers = SignerSerializer(many=True)

    class Meta:
        model = MultisigWallet
        fields = ['id', 'walletHash', 'walletName', 'walletDescription', 'signers', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def create(self, validated_data):
        signers_data = validated_data.pop('signers')
        
        # Remove fields that don't exist in the model
        validated_data.pop('walletDescription', None)
        
        # Validate that pubkey_zero values are unique within this wallet
        pubkey_zeros = [
            signer_data.get('pubkey_zero') 
            for signer_data in signers_data 
            if signer_data.get('pubkey_zero')
        ]
        if len(pubkey_zeros) != len(set(pubkey_zeros)):
            raise ValidationError({
                'signers': 'Each signer must have a unique pubkeyZero within the wallet.'
            })
        
        LOGGER.info(f"validated_data: {validated_data}")
        with transaction.atomic():
            wallet = MultisigWallet.objects.create(**validated_data)

            for signer_data in signers_data:
                Signer.objects.create(wallet=wallet, **signer_data)
            
            return wallet