from rest_framework import serializers
from .models import (
    MultisigWallet,
    Signer,
    Transaction,
    SignerTransactionSignature
)

class SignerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Signer
        fields = ['xpub', 'derivation_path']

# serializers.py
from rest_framework import serializers
from .models import MultisigWallet, Signer
from .crypto_utils import verify_signature  # from previous utility
from django.conf import settings
import redis

redis_client = redis.Redis.from_url(settings.REDISKV)

class SignerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Signer
        fields = ['xpub', 'derivation_path']

class MultisigWalletSerializer(serializers.ModelSerializer):
    signers = SignerSerializer(many=True, write_only=True)

    # Extra fields for authentication
    claimed_xpub = serializers.CharField(write_only=True)
    signature = serializers.CharField(write_only=True)
    message = serializers.CharField(write_only=True)

    class Meta:
        model = MultisigWallet
        fields = ['id', 'm', 'n', 'template', 'signers', 'claimed_xpub', 'signature', 'message']

    def validate(self, data):
        claimed_xpub = data['claimed_xpub']
        signature = data['signature']
        message = data['message']
        signers = data.get("signers", [])

        # Ensure claimed_xpub is one of the provided signers
        xpubs = [s["xpub"] for s in signers]
        if claimed_xpub not in xpubs:
            raise serializers.ValidationError("The claimed xpub must be one of the wallet signers.")

        # Get derivation path for that xpub (needed for verification)
        signer_info = next(s for s in signers if s['xpub'] == claimed_xpub)
        derivation_path = signer_info.get('derivation_path', "m/44'/145'/0'/0/0")

        # Extract nonce from message and validate it
        try:
            nonce = message.split("nonce:")[-1].strip()
        except Exception:
            raise serializers.ValidationError("Invalid message format.")

        nonce_key = f"nonce:{nonce}"
        if not redis_client.get(nonce_key):
            raise serializers.ValidationError("Invalid or expired nonce.")

        # Perform signature verification
        if not verify_signature(message, signature, claimed_xpub, derivation_path):
            raise serializers.ValidationError("Signature verification failed.")

        return data

    def create(self, validated_data):
        signers_data = validated_data.pop('signers')
        validated_data.pop('claimed_xpub')
        validated_data.pop('signature')
        validated_data.pop('message')

        wallet = MultisigWallet.objects.create(**validated_data)

        for signer_data in signers_data:
            signer, _ = Signer.objects.get_or_create(
                xpub=signer_data['xpub'],
                derivation_path=signer_data['derivation_path']
            )
            wallet.signers.add(signer)

        return wallet



class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = ['id', 'txid', 'unsigned_hex', 'unsigned_hex_hash']


class SignerTransactionSignatureSerializer(serializers.ModelSerializer):
    signer = serializers.PrimaryKeyRelatedField(queryset=Signer.objects.all())
    transaction = serializers.PrimaryKeyRelatedField(queryset=Transaction.objects.all())

    class Meta:
        model = SignerTransactionSignature
        fields = [
            'id',
            'input_index',
            'transaction',
            'signer',
            'signature',
            'signature_algo',
            'signature_script_placeholder',
            'sighash'
        ]
