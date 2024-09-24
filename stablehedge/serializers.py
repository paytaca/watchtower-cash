from rest_framework import serializers
from django.db import transaction
from django.utils import timezone

from stablehedge import models
from stablehedge.js.runner import ScriptFunctions
from stablehedge.utils.transaction import validate_utxo_data

from anyhedge import models as anyhedge_models


class UtxoSerializer(serializers.Serializer):
    txid = serializers.CharField()
    vout = serializers.IntegerField()
    satoshis = serializers.IntegerField()

    category = serializers.CharField(required=False)
    capability = serializers.CharField(required=False)
    commitment = serializers.CharField(required=False)
    amount = serializers.IntegerField(required=False)

    locking_bytecode = serializers.CharField(required=False)
    unlocking_bytecode = serializers.CharField(required=False)

    class Meta:
        ref_name = "stablehedge_UtxoSerializer"


class FiatTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FiatToken
        fields = [
            "category",
            "genesis_supply",

            "currency",
            "decimals",
        ]


class RedemptionContractSerializer(serializers.ModelSerializer):
    fiat_token = FiatTokenSerializer()
    network = serializers.CharField(required=False, default="chipnet", write_only=True)

    class Meta:
        model = models.RedemptionContract
        fields = [
            "network",
            "address",
            "fiat_token",
            "auth_token_id",
            "price_oracle_pubkey",
        ]

        extra_kwargs = dict(
            address=dict(read_only=True),
        )

    def validate(self, data):
        compile_data = ScriptFunctions.compileRedemptionContract(dict(
            params=dict(
                authKeyId=data["auth_token_id"],
                tokenCategory=data["fiat_token"]["category"],
                oraclePublicKey=data["price_oracle_pubkey"],
            ),
            options=dict(network=data["network"], addressType="p2sh32"),
        ))
        data["address"] = compile_data["address"]
        existing = models.RedemptionContract.objects.filter(address=data["address"]).first()
        if existing and (not self.instance or self.instance.id != existing.id):
            raise serializers.ValidationError("This contract already exists")
        return data

    @transaction.atomic
    def create(self, validated_data):
        fiat_token_data = validated_data.pop("fiat_token")
        fiat_token = models.FiatToken(**fiat_token_data)
        fiat_token.save()
        validated_data["fiat_token"] = fiat_token
        return super().create(validated_data)


class SweepRedemptionContractSerializer(serializers.Serializer):
    redemption_contract_address = serializers.SlugRelatedField(
        queryset=models.RedemptionContract.objects,
        slug_field="address", source="redemption_contract",
        write_only=True,
    )
    recipient_address = serializers.CharField(write_only=True)
    auth_key_recipient_address = serializers.CharField(write_only=True)
    auth_key_utxo = UtxoSerializer(write_only=True)
    tx_hex = serializers.CharField(read_only=True)

    def save(self):
        validated_data = {**self.validated_data}
        redemption_contract = validated_data["redemption_contract"]
        auth_key_utxo_data = validated_data["auth_key_utxo"]

        return ScriptFunctions.sweepRedemptionContract(dict(
            contractOpts=dict(
                params=dict(
                    authKeyId=redemption_contract.auth_token_id,
                    tokenCategory=redemption_contract.fiat_token.category,
                    oraclePublicKey=redemption_contract.price_oracle_pubkey,
                ),
                options=dict(network=redemption_contract.network, addressType="p2sh32"),
            ),
            authKeyUtxo=dict(
                txid=auth_key_utxo_data["txid"],
                vout=auth_key_utxo_data["vout"],
                satoshis=auth_key_utxo_data["satoshis"],
                token=dict(
                    category=auth_key_utxo_data["category"],
                    amount=auth_key_utxo_data["amount"],
                    nft=dict(
                        commitment=auth_key_utxo_data["commitment"],
                        capability=auth_key_utxo_data["capability"],
                    ),
                ),
                unlockingBytecode=auth_key_utxo_data["unlocking_bytecode"],
                lockingBytecode=auth_key_utxo_data["locking_bytecode"],
            ),
            recipientAddress=validated_data["recipient_address"],
            authKeyRecipient=validated_data["auth_key_recipient_address"],
        ))


class PriceMessageSerializer(serializers.Serializer):
    message = serializers.CharField()
    signature = serializers.CharField()
    pubkey = serializers.CharField()

    message_timestamp = serializers.DateTimeField(read_only=True)
    price_value = serializers.IntegerField(read_only=True)
    price_sequence = serializers.IntegerField(read_only=True)
    message_sequence = serializers.IntegerField(read_only=True)

    def validate(self, data):
        parse_result = ScriptFunctions.parsePriceMessage(dict(
            priceMessage=data["message"],
            signature=data["signature"],
            publicKey=data["pubkey"],
        ))

        if "error" in parse_result and not parse_result.get("success"):
            raise serializers.ValidationError(parse_result["error"])

        price_data = parse_result["priceData"]
        msg_timestamp = timezone.datetime.fromtimestamp(price_data["timestamp"] / 1000)
        msg_timestamp = timezone.make_aware(msg_timestamp)
            
        data["message_timestamp"] = msg_timestamp
        data["price_value"] = price_data["price"]
        data["price_sequence"] = price_data["dataSequence"]
        data["message_sequence"] = price_data["msgSequence"]
        return data


class RedemptionContractTransactionSerializer(serializers.ModelSerializer):
    redemption_contract_address = serializers.SlugRelatedField(
        queryset=models.RedemptionContract.objects,
        slug_field="address", source="redemption_contract",
        write_only=True,
    )
    price_oracle_message = PriceMessageSerializer()
    utxo = UtxoSerializer()

    class Meta:
        model = models.RedemptionContractTransaction
        fields = [
            "redemption_contract_address",
            "price_oracle_message",
            "status",
            "transaction_type",
            "txid",
            "utxo",
            "resolved_at",
            "created_at",
        ]

        extra_kwargs = dict(
            status=dict(read_only=True),
            txid=dict(read_only=True),
            resolved_at=dict(read_only=True),
            created_at=dict(read_only=True),
        )

    def validate(self, data):
        redemption_contract = data["redemption_contract"]
        utxo_data = data["utxo"]
        transaction_type = data["transaction_type"]
        require_cashtoken = transaction_type == models.RedemptionContractTransaction.Type.REDEEM
        valid_utxo_data = validate_utxo_data(
            utxo_data,
            require_cashtoken=require_cashtoken,
            require_unlock=True,
            raise_error=False,
        )
        if valid_utxo_data is not True:
            raise serializers.ValidationError(dict(utxo=valid_utxo_data))

        if transaction_type == models.RedemptionContractTransaction.Type.REDEEM:
            if utxo_data["category"] != redemption_contract.fiat_token.category:
                raise serializers.ValidationError("Utxo category does not match with redemption contract")

        return data

    def save_price_message(self, price_message_data):
        data = {**price_message_data}
        pubkey = data.pop("pubkey")
        message = data.pop("message")
        obj, _ = anyhedge_models.PriceOracleMessage.objects.update_or_create(
            pubkey=pubkey,
            message=message,
            defaults=data,
        )
        return obj

    @transaction.atomic
    def create(self, validated_data):
        price_message_data = validated_data.pop("price_oracle_message")
        validated_data["price_oracle_message"] = self.save_price_message(price_message_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        raise serializers.ValidationError("Invalid action")
