from rest_framework import serializers
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from drf_yasg.utils import swagger_serializer_method

from stablehedge.apps import LOGGER
from stablehedge import models
from stablehedge.functions.anyhedge import place_short_proposal
from stablehedge.functions.redemption_contract import get_24hr_volume_sats
from stablehedge.js.runner import ScriptFunctions
from stablehedge.utils.blockchain import get_locktime
from stablehedge.utils.transaction import (
    validate_utxo_data,
    utxo_data_to_cashscript,
    tx_model_to_cashscript,
    token_to_satoshis,
    satoshis_to_token,
)
from stablehedge.utils.encryption import decrypt_wif_safe
from stablehedge.utils.wallet import (
    is_valid_wif,
    wif_to_pubkey,
)

from anyhedge import models as anyhedge_models
from anyhedge import serializers as anyhedge_serializers
from main import models as main_models


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


class TxOutputSerializer(serializers.Serializer):
    to = serializers.CharField()
    satoshis = serializers.IntegerField()

    category = serializers.CharField(required=False)
    capability = serializers.CharField(required=False)
    commitment = serializers.CharField(required=False)
    amount = serializers.IntegerField(required=False)


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
    redeemable = serializers.IntegerField(read_only=True)
    reserve_supply = serializers.IntegerField(read_only=True)
    volume_24_hr = serializers.SerializerMethodField()
    treasury_contract_address = serializers.CharField(read_only=True)

    class Meta:
        model = models.RedemptionContract
        fields = [
            "address",
            "fiat_token",
            "auth_token_id",
            "price_oracle_pubkey",

            "redeemable",
            "reserve_supply",
            "volume_24_hr",
            "treasury_contract_address",
        ]

        extra_kwargs = dict(
            address=dict(read_only=True),
        )

    @swagger_serializer_method(serializer_or_field=serializers.DecimalField(max_digits=18, decimal_places=0))
    def get_volume_24_hr(self, obj):
        return get_24hr_volume_sats(obj.address)

    def validate(self, data):
        compile_data = ScriptFunctions.compileRedemptionContract(dict(
            params=dict(
                authKeyId=data["auth_token_id"],
                tokenCategory=data["fiat_token"]["category"],
                oraclePublicKey=data["price_oracle_pubkey"],
            ),
            options=dict(network=settings.BCH_NETWORK, addressType="p2sh32"),
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
    locktime = serializers.IntegerField(required=False)
    consolidated = serializers.BooleanField(default=False)
    recipient_address = serializers.CharField(write_only=True)
    auth_key_recipient_address = serializers.CharField(write_only=True)
    auth_key_utxo = UtxoSerializer(write_only=True)
    tx_hex = serializers.CharField(read_only=True)

    def save(self):
        validated_data = {**self.validated_data}
        redemption_contract = validated_data["redemption_contract"]
        auth_key_utxo_data = validated_data["auth_key_utxo"]
        consolidated = validated_data["consolidated"]
        locktime = validated_data.get("locktime")
        if not isinstance(locktime, int):
            locktime = get_locktime()

        utxo_qs = main_models.Transaction.objects \
            .filter(address__address=redemption_contract.address, spent=False)

        utxos = [tx_model_to_cashscript(obj) for obj in utxo_qs]

        if consolidated:
            return ScriptFunctions.sweepRedemptionContract(dict(
                contractOpts=redemption_contract.contract_opts,
                locktime=locktime,
                contractUtxos=utxos,
                authKeyUtxo=utxo_data_to_cashscript(auth_key_utxo_data),
                recipientAddress=validated_data["recipient_address"],
                authKeyRecipient=validated_data["auth_key_recipient_address"],
            ))
        else:
            return ScriptFunctions.transferRedemptionContractAssets(dict(
                contractOpts=redemption_contract.contract_opts,
                locktime=locktime,
                utxos=utxos,
                authKeyUtxo=utxo_data_to_cashscript(auth_key_utxo_data),
                recipientAddress=validated_data["recipient_address"],
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
        msg_timestamp = timezone.datetime.fromtimestamp(price_data["timestamp"])
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
    fiat_token = FiatTokenSerializer(source="redemption_contract.fiat_token", read_only=True)

    class Meta:
        model = models.RedemptionContractTransaction
        fields = [
            "id",
            "redemption_contract_address",
            "price_oracle_message",
            "wallet_hash",
            "status",
            "transaction_type",
            "txid",
            "utxo",
            "resolved_at",
            "created_at",

            "fiat_token",
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

        tx_obj = main_models.Transaction.objects.filter(
            txid=utxo_data["txid"], index=utxo_data["vout"]).first()

        if tx_obj and tx_obj.spent:
            raise serializers.ValidationError("UTXO spent")

        redemption_contract_tx_obj = models.RedemptionContractTransaction.objects.filter(
            status=models.RedemptionContractTransaction.Status.PENDING,
            utxo__txid=utxo_data["txid"],
            utxo__vout=utxo_data["vout"],
        ).first()

        if redemption_contract_tx_obj:
            if not self.instance or self.instance.id != redemption_contract_tx_obj.id:
                raise serializers.ValidationError(
                    f"UTXO in use by tx#{redemption_contract_tx_obj.id}"
                )

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


class RedemptionContractTransactionHistorySerializer(serializers.ModelSerializer):
    """
        Intended for returning minimal data as stablehedge wallet history 
    """
    redemption_contract_address = serializers.CharField(source="redemption_contract.address", read_only=True)
    satoshis = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()
    category = serializers.CharField(source="redemption_contract.fiat_token.category", read_only=True)
    price_value = serializers.CharField(source="price_oracle_message.price_value", read_only=True)

    class Meta:
        model = models.RedemptionContractTransaction
        fields = [
            "id",
            "redemption_contract_address",
            "transaction_type",
            "status",
            "txid",
            "category",
            "price_value",
            "satoshis",
            "amount",
            "result_message",
            "resolved_at",
            "created_at",
        ]

    @swagger_serializer_method(serializer_or_field=serializers.IntegerField)
    def get_satoshis(self, obj):
        try:
            satoshis = obj.utxo["satoshis"] - 2000
            amount = obj.utxo.get("amount", 0)
        except (TypeError, KeyError) as exception:
            LOGGER.exception(exception)
            return None

        price_units_per_bch = obj.price_oracle_message.price_value

        Type = models.RedemptionContractTransaction.Type
        if obj.transaction_type in [Type.DEPOSIT, Type.INJECT]:
            return satoshis
        elif obj.transaction_type in [Type.REDEEM]:
            return token_to_satoshis(amount, price_units_per_bch)

    @swagger_serializer_method(serializer_or_field=serializers.IntegerField)
    def get_amount(self, obj):
        try:
            satoshis = obj.utxo["satoshis"] - 2000
            amount = obj.utxo.get("amount", 0)
        except (TypeError, KeyError) as exception:
            LOGGER.exception(exception)
            return None

        price_units_per_bch = obj.price_oracle_message.price_value

        Type = models.RedemptionContractTransaction.Type
        if obj.transaction_type in [Type.DEPOSIT, Type.INJECT]:
            return satoshis_to_token(satoshis, price_units_per_bch)
        elif obj.transaction_type in [Type.REDEEM]:
            return amount


class TreasuryContractSerializer(serializers.ModelSerializer):
    redemption_contract_address = serializers.SlugRelatedField(
        queryset=models.RedemptionContract.objects,
        slug_field="address", source="redemption_contract",
    )
    funding_wif_pubkey = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = models.TreasuryContract
        fields = [
            "redemption_contract_address",
            "address",
            "auth_token_id",
            "pubkey1",
            "pubkey2",
            "pubkey3",
            "pubkey4",
            "pubkey5",
            "funding_wif_pubkey",
        ]

        extra_kwargs = dict(
            address=dict(read_only=True),
        )

    @swagger_serializer_method(serializer_or_field=serializers.CharField)
    def get_funding_wif_pubkey(self, obj):
        wif = decrypt_wif_safe(obj.encrypted_funding_wif)
        if not wif:
            return
        return wif_to_pubkey(wif)

    def validate(self, data):
        compile_data = ScriptFunctions.compileTreasuryContract(dict(
            params=dict(
                authKeyId=data["auth_token_id"],
                pubkeys=[
                    data["pubkey1"],
                    data["pubkey2"],
                    data["pubkey3"],
                    data["pubkey4"],
                    data["pubkey5"],
                ]
            ),
            options=dict(network=settings.BCH_NETWORK, addressType="p2sh32"),
        ))
        data["address"] = compile_data["address"]
        existing = models.TreasuryContract.objects.filter(address=data["address"]).first()
        if existing and (not self.instance or self.instance.id != existing.id):
            raise serializers.ValidationError("This contract already exists")
        return data


class SweepTreasuryContractSerializer(serializers.Serializer):
    treasury_contract_address = serializers.SlugRelatedField(
        queryset=models.TreasuryContract.objects,
        slug_field="address", source="treasury_contract",
        write_only=True,
    )
    recipient_address = serializers.CharField(write_only=True)
    auth_key_recipient_address = serializers.CharField(write_only=True)
    auth_key_utxo = UtxoSerializer(write_only=True)
    tx_hex = serializers.CharField(read_only=True)

    def save(self):
        validated_data = {**self.validated_data}
        treasury_contract = validated_data["treasury_contract"]
        auth_key_utxo_data = validated_data["auth_key_utxo"]

        return ScriptFunctions.sweepTreasuryContract(dict(
            contractOpts=treasury_contract.contract_opts,
            authKeyUtxo=utxo_data_to_cashscript(auth_key_utxo_data),
            recipientAddress=validated_data["recipient_address"],
            authKeyRecipient=validated_data["auth_key_recipient_address"],
        ))

class ShortProposalSettlementServiceData(anyhedge_serializers.SettlementServiceSerializer):
    pubkey = serializers.CharField()

    class Meta:
        ParentMeta = anyhedge_serializers.SettlementServiceSerializer.Meta
        model = ParentMeta.model
        fields = [
            *ParentMeta.fields,
            "pubkey",
        ]

class TreasuryContractShortProposal(serializers.Serializer):
    treasury_contract_address = serializers.CharField()
    short_contract_address = serializers.CharField()
    settlement_service = ShortProposalSettlementServiceData()
    funding_utxo_tx_hex = serializers.CharField()

    def save(self):
        validated_data = {**self.valdiated_data}
        return place_short_proposal(**validated_data)
