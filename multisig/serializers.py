from rest_framework import serializers
from .models import (
    MultisigWallet,
    Signer,
    Transaction,
    SignerTransactionSignature
)


class MultisigWalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = MultisigWallet
        fields = ['id', 'm', 'n', 'template']


class SignerSerializer(serializers.ModelSerializer):
    wallet = serializers.PrimaryKeyRelatedField(queryset=MultisigWallet.objects.all())

    class Meta:
        model = Signer
        fields = ['id', 'xpub', 'derivation_path', 'wallet']


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
