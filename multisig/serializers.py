from rest_framework import serializers
from django.db import transaction

from .models import (
    MultisigWallet,
    Signer,
    Transaction,
    SignerTransactionSignature,
    MultisigWalletSigner
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

nonce_cache = settings.REDISKV

class SignerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Signer
        fields = ['xpub', 'derivation_path']

class MultisigWalletSerializer(serializers.ModelSerializer):
    signers = SignerSerializer(many=True, write_only=True)

    # Extra fields for authentication
    claimed_xpub = serializers.CharField(write_only=True)
    creator_signer_index = serializers.IntegerField(write_only=True)
    signature = serializers.CharField(write_only=True)
    message = serializers.CharField(write_only=True)

    class Meta:
        model = MultisigWallet
        fields = ['id', 'm', 'n', 'template', 'signers', 'creator_signer_index', 'signature', 'message']

    def validate(self, data):

        if data['m'] > data['n']:
            raise serializers.ValidationError("m cannot be greater than n.")

        signers_dict = data.get("signers", {})

        creator_signer_index = data['creator_signer_index']

        if creator_signer_index < 1 or creator_signer_index > len(signers_dict.keys()):
            raise serializers.ValidationError(f"Invalid signer index: {signer_index}.")

        creator_claimed_xpub = data['signers'][creator_signer_index]['xpub']
        signature = data['signature']
        message = data['message']

        xpubs = [s["xpub"] for s in signers_dict.values()]
        if creator_claimed_xpub not in xpubs:
            raise serializers.ValidationError("The claimed xpub must be one of the wallet signers.")

        try:
            signer_info = next(s for s in signers_dict.values() if s['xpub'] == creator_claimed_xpub)
        except StopIteration:
            raise serializers.ValidationError("Signer information for claimed xpub not found.")

        derivation_path = signer_info.get('derivation_path', "m/44'/145'/0'/0/0")
        
        nonce = message
        try:
            nonce = nonce.split("nonce:")[-1].strip()
        except Exception:
            raise serializers.ValidationError("Invalid message format.")

        if not nonce_cache.get(nonce):
            raise serializers.ValidationError("Invalid or expired nonce.")

        if not verify_signature(message, signature, creator_claimed_xpub, derivation_path):
            raise serializers.ValidationError("Signature verification failed.")

        return data

    def create(self, validated_data):
        signers_dict = validated_data.pop('signers')
        validated_data.pop('creator_signer_index')
        validated_data.pop('signature')
        validated_data.pop('message')

        with transaction.atomic():
            wallet = MultisigWallet.objects.create(**validated_data)

            for index_str, signer_data in signers_dict.items():
                try:
                    index = int(index_str)
                except ValueError:
                    raise serializers.ValidationError(f"Signer index '{index_str}' must be an integer.")

                signer, _ = Signer.objects.get_or_create(
                    xpub=signer_data['xpub'],
                    derivation_path=signer_data.get('derivation_path', "m/44'/145'/0'/0/0")
                )
                MultisigWalletSigner.objects.create(wallet=wallet, signer=signer, index=index)

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