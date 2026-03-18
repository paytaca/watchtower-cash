import logging
from django.db import transaction
from rest_framework import serializers
from typing import Dict
from main.models import Transaction
from multisig.models.wallet import MultisigWallet, Signer, KeyRecord

LOGGER = logging.getLogger(__name__)

class KeyRecordReadOnlySerializer(serializers.ModelSerializer):
    audienceAuthPublicKey = serializers.CharField(
        source="audience_auth_public_key", read_only=True
    )
    publisherServerId = serializers.PrimaryKeyRelatedField(
        source="publisher", read_only=True
    )

    class Meta:
        model = KeyRecord
        fields = [
            "id",
            "publisherServerId",
            "key_record",
            "audienceAuthPublicKey",
            "wallet",
        ]
        read_only_fields = [
            "id",
            "publisherServerId",
            "key_record",
            "audienceAuthPublicKey",
            "wallet",
        ]


class SignerSerializer(serializers.ModelSerializer):
    masterFingerprint = serializers.CharField(source="master_fingerprint")
    derivationPath = serializers.CharField(source="derivation_path")
    walletDescriptorWrappedDek = serializers.CharField(
        source="wallet_descriptor_wrapped_dek"
    )
    wallet = serializers.PrimaryKeyRelatedField(read_only=True)
    coordinatorKeyRecord = serializers.CharField(write_only=True)
    authPublicKey = serializers.CharField(source="auth_public_key")

    class Meta:
        model = Signer
        fields = [
            "id",
            "name",
            "masterFingerprint",
            "derivationPath",
            "walletDescriptorWrappedDek",
            "wallet",
            "coordinatorKeyRecord",
            "authPublicKey",
        ]


class MultisigWalletSerializer(serializers.ModelSerializer):
    signers = SignerSerializer(many=True, required=False)
    walletDescriptorId = serializers.CharField(source="wallet_descriptor_id")
    walletHash = serializers.CharField(source="wallet_hash")
    walletDescriptor = serializers.CharField(source="wallet_descriptor")
    keyRecords = KeyRecordReadOnlySerializer(
        source="key_records", many=True, required=False
    )
    coordinatorServerId = serializers.PrimaryKeyRelatedField(
        source="coordinator", read_only=True
    )

    class Meta:
        model = MultisigWallet
        fields = [
            "id",
            "name",
            "walletHash",
            "walletDescriptorId",
            "walletDescriptor",
            "version",
            "created_at",
            "deleted_at",
            "updated_at",
            "coordinatorServerId",
            "signers",
            "keyRecords",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "deleted_at",
            "keyRecords",
            "coordinatorServerId",
        ]

    def create(self, validated_data):
        coordinator = self.context["coordinator"]
        signers_data = validated_data.pop("signers", [])
        wallet_descriptor_id = validated_data.get("wallet_descriptor_id")

        with transaction.atomic():
            wallet = MultisigWallet.objects.filter(
                coordinator=coordinator, wallet_descriptor_id=wallet_descriptor_id
            ).first()

            if wallet:
                return wallet

            wallet = MultisigWallet.objects.create(
                coordinator=coordinator, **validated_data
            )

            for signer_data in signers_data:
                coordinatorKeyRecordHex = signer_data.pop("coordinatorKeyRecord", None)
                if coordinatorKeyRecordHex:
                    KeyRecord.objects.get_or_create(
                        publisher=coordinator,
                        key_record=coordinatorKeyRecordHex,
                        defaults={
                            "publisher": coordinator,
                            "key_record": coordinatorKeyRecordHex,
                            "audience_auth_public_key": signer_data["auth_public_key"],
                        },
                        wallet=wallet,
                    )
                Signer.objects.create(wallet=wallet, **signer_data)

        return wallet


class MultisigWalletUtxoSerializer(serializers.Serializer):
    txid = serializers.CharField()
    vout = serializers.SerializerMethodField()
    satoshis = serializers.SerializerMethodField()
    height = serializers.SerializerMethodField()
    coinbase = serializers.SerializerMethodField()
    token = serializers.SerializerMethodField()

    def get_vout(self, obj):
        return obj.index

    def get_satoshis(self, obj):
        return obj.value

    def get_height(self, obj):
        if obj.blockheight:
            return obj.blockheight.number
        else:
            return 0

    def get_coinbase(self, obj) -> bool:
        return False  # We just assume watchtower is not indexing coinbase txs, verify.

    def get_token(self, obj) -> Dict[str, str]:

        token = {}

        if obj.amount:
            token["amount"] = str(obj.amount)

        if obj.cashtoken_ft and obj.cashtoken_ft.category:
            token["category"] = obj.cashtoken_ft.category

        if obj.cashtoken_nft:
            if not token.get("category"):
                token["category"] = obj.cashtoken_nft.category
            token["nft"] = {
                "commitment": obj.cashtoken_nft.commitment,
                "capability": obj.cashtoken_nft.capability,
            }
        if len(token.keys()) > 0:
            return token

        return None

    class Meta:
        model = Transaction
        fields = ["txid", "vout", "satoshis", "height", "coinbase", "token"]
