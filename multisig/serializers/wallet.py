from rest_framework import serializers
from .models import MultisigWallet, Signer, MultisigWalletDescriptor
from django.db import transaction

class MultisigWalletDescriptorSerializer(serializers.ModelSerializer):
    class Meta:
        model = MultisigWalletDescriptor
        fields = ['descriptor']

class SignerSerializer(serializers.ModelSerializer):
    # We use this to capture the descriptor from the input data
    walletDescriptor = serializers.CharField(write_only=True)

    class Meta:
        model = Signer
        fields = ['name', 'xpub_hash', 'walletDescriptor']
        # Map the camelCase input to the snake_case model field
        extra_kwargs = {
            'xpub_hash': {'source': 'xpubHash', 'required': False}
        }

class MultisigWalletSerializer(serializers.ModelSerializer):
    # Map 'signers' input to the nested serializer
    signers = SignerSerializer(many=True)

    class Meta:
        model = MultisigWallet
        fields = ['name', 'wallet_hash', 'signers']
        extra_kwargs = {
            'wallet_hash': {'source': 'walletHash'}
        }

    def create(self, validated_data):
        signers_data = validated_data.pop('signers')
        
        with transaction.atomic():
            wallet = MultisigWallet.objects.create(**validated_data)

            for signer_data in signers_data:
                descriptor_str = signer_data.pop('walletDescriptor')
                
                signer = Signer.objects.create(wallet=wallet, **signer_data)

                MultisigWalletDescriptor.objects.create(
                    signer=signer, 
                    descriptor=descriptor_str
                )
            
            return wallet