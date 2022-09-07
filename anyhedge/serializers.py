import pytz
from datetime import datetime, timedelta
from django.db import transaction
from rest_framework import serializers

from .models import (
    LongAccount,
    HedgePosition,
    HedgeFundingProposal,
    HedgePositionOffer,
)
from .utils.address import match_pubkey_to_cash_address
from .utils.contract import create_contract
from .utils.liquidity import (
    consume_long_account_allowance,
    get_position_offer_suggestions,
)
from .utils.websocket import (
    send_settlement_update,
    send_funding_tx_update,
)


class FundingProposalSerializer(serializers.Serializer):
    hedge_address = serializers.CharField()
    position = serializers.CharField() # hedge | long
    tx_hash = serializers.CharField()
    tx_index = serializers.IntegerField()
    tx_value = serializers.IntegerField()
    script_sig = serializers.CharField()
    pubkey = serializers.CharField(required=False)
    input_tx_hashes = serializers.ListField(
        child=serializers.CharField(),
        required=False
    )

    def validate_hedge_address(value):
        try:
            HedgePosition.objects.get(address=value)
        except HedgePosition.DoesNotExist:
            raise serializers.ValidationError("Hedge position does not exist")

        return value

    def validate_position(value):
        if position != "hedge" or position != "long":
            raise serializers.ValidationError("Position must be \"hedge\" or \"long\"")
        return value

    @transaction.atomic()
    def create(self, validated_data):
        hedge_address = validated_data.pop("hedge_address")
        position = validated_data.pop("position")
        hedge_pos_obj = HedgePosition.objects.get(hedge_address.value)

        update_hedge_obj = True

        if position == "hedge" and hedge_pos_obj.hedge_funding_proposal:
            funding_proposal = hedge_pos_obj.hedge_funding_proposal
            update_hedge_obj = False
        elif position == "long" and hedge_pos_obj.long_funding_proposal:
            funding_proposal = hedge_pos_obj.long_funding_proposal
            update_hedge_obj = False

        funding_proposal.tx_hash = validated_data["tx_hash"]
        funding_proposal.tx_index = validated_data["tx_index"]
        funding_proposal.tx_value = validated_data["tx_value"]
        funding_proposal.script_sig = validated_data["script_sig"]
        funding_proposal.pubkey = validated_data["pubkey"]
        funding_proposal.input_tx_hashes = validated_data.get("pubkey", None)
        funding_proposal.save()

        if update_hedge_obj:
            if position == "hedge":
                hedge_pos_obj.hedge_funding_proposal = funding_proposal
            elif position == "long":
                hedge_pos_obj.long_funding_proposal = funding_proposal
            hedge_pos_obj.save()

        send_funding_tx_update(hedge_pos_obj, position=position)
        return funding_proposal


class LongAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = LongAccount
        fields = [
            "id",
            "wallet_hash",
            "address_path",
            "address",
            "pubkey",

            "min_auto_accept_duration",
            "max_auto_accept_duration",
            "auto_accept_allowance",
        ]

    def validate(self, data):
        if "pubkey" in data and "address" in data:
            if not match_pubkey_to_cash_address(data["pubkey"], data["address"]):
                raise serializers.ValidationError("public key & address does not match")
        return data


class HedgeFundingProposalSerializer(serializers.ModelSerializer):
    class Meta:
        model = HedgeFundingProposal
        fields = [
            "tx_hash",
            "tx_index",
            "tx_value",
            "script_sig",
            "pubkey",
            "input_tx_hashes",
        ]
        

class HedgePositionSerializer(serializers.ModelSerializer):
    hedge_funding_proposal = HedgeFundingProposalSerializer()
    long_funding_proposal = HedgeFundingProposalSerializer()
    start_timestamp = serializers.SerializerMethodField()
    maturity_timestamp = serializers.SerializerMethodField()

    class Meta:
        model = HedgePosition
        fields = [
            "id",
            "address",
            "anyhedge_contract_version",
            "satoshis",
            "start_timestamp",
            "maturity_timestamp",
            "hedge_address",
            "hedge_pubkey",
            "long_address",
            "long_pubkey",
            "oracle_pubkey",
            "start_price",
            "low_liquidation_multiplier",
            "high_liquidation_multiplier",
            "funding_tx_hash",
            "hedge_funding_proposal",
            "long_funding_proposal",
        ]

    def get_start_timestamp(self, obj):
        return datetime.timestamp(obj.start_timestamp)

    def get_maturity_timestamp(self, obj):
        return datetime.timestamp(obj.maturity_timestamp)

    def validate(self, data):
        if not match_pubkey_to_cash_address(data["hedge_pubkey"], data["hedge_address"]):
            raise serializers.ValidationError("hedge public key & address does not match")

        if not match_pubkey_to_cash_address(data["long_pubkey"], data["long_address"]):
            raise serializers.ValidationError("long public key & address does not match")
        return data


class HedgePositionOfferSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)
    hedge_position = HedgePositionSerializer(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    auto_match = serializers.BooleanField(default=False)
    hedge_funding_proposal = HedgeFundingProposalSerializer(required=False)

    class Meta:
        model = HedgePositionOffer
        fields = [
            "status",
            "wallet_hash",
            "satoshis",
            "duration_seconds",
            "high_liquidation_multiplier",
            "low_liquidation_multiplier",
            "hedge_address",
            "hedge_pubkey",
            "hedge_position",
            "created_at",
            "auto_match",
            "hedge_funding_proposal",
        ]

    def validate(self, data):
        if not match_pubkey_to_cash_address(data["hedge_pubkey"], data["hedge_address"]):
            raise serializers.ValidationError("public key & address does not match")

        return data

    @transaction.atomic()
    def create(self, validated_data, *args, **kwargs):
        auto_match = validated_data.pop("auto_match", False)
        hedge_funding_proposal_data = validated_data.pop("hedge_funding_proposal", None)
        instance = super().create(validated_data, *args, **kwargs)

        if hedge_funding_proposal_data is not None:
            hedge_funding_proposal_serializer = HedgeFundingProposalSerializer(data=hedge_funding_proposal_data)
            hedge_funding_proposal_serializer.is_valid(raise_exception=True)
            hedge_funding_proposal = hedge_funding_proposal_serializer.save()
            instance.hedge_funding_proposal = hedge_funding_proposal
            instance.save()

        if auto_match:
            long_accounts = get_position_offer_suggestions(
                amount=instance.satoshis,
                duration_seconds=instance.duration_seconds,
                low_liquidation_multiplier=instance.low_liquidation_multiplier,
                high_liquidation_multiplier=instance.high_liquidation_multiplier,
            )
            if long_accounts:
                long_account = long_accounts[0]
                response = create_contract(
                    satoshis=instance.satoshis,
                    low_price_multiplier=instance.low_liquidation_multiplier,
                    high_price_multiplier=instance.high_liquidation_multiplier,
                    duration_seconds=instance.duration_seconds,
                    hedge_address=instance.hedge_address,
                    hedge_pubkey=instance.hedge_pubkey,
                    short_address=long_account.address,
                    short_pubkey=long_account.pubkey,
                )

                if "success" in response and response["success"]:
                    contract_data = response["contractData"]
                    settle_hedge_position_offer_data = {
                        "address": contract_data["address"],
                        "anyhedge_contract_version": contract_data["version"],
                        "oracle_pubkey": contract_data["metadata"]["oraclePublicKey"],
                        "oracle_price": contract_data["metadata"]["startPrice"],
                        "oracle_timestamp": contract_data["metadata"]["startTimestamp"],
                        "long_wallet_hash": long_account.wallet_hash,
                        "long_address": contract_data["metadata"]["longAddress"],
                        "long_pubkey": contract_data["metadata"]["longPublicKey"],
                    }

                    settle_hedge_position_offer_serializer = SettleHedgePositionOfferSerializer(
                        data=settle_hedge_position_offer_data,
                        hedge_position_offer=instance,
                        auto_settled=True,
                    )
                    settle_hedge_position_offer_serializer.is_valid(raise_exception=True)
                    instance = settle_hedge_position_offer_serializer.save()
                else:
                    raise Exception("Error creating contract data")
            elif instance.hedge_funding_proposal:
                lp_matchmaking_result = match_hedge_position_to_liquidity_provider(instance)
                if lp_matchmaking_result["success"]:
                    contract_data = response["contractData"]
                    settle_hedge_position_offer_data = {
                        "address": contract_data["address"],
                        "anyhedge_contract_version": contract_data["version"],
                        "oracle_pubkey": contract_data["metadata"]["oraclePublicKey"],
                        "oracle_price": contract_data["metadata"]["startPrice"],
                        "oracle_timestamp": contract_data["metadata"]["startTimestamp"],
                        "long_wallet_hash": "",
                        "long_address": contract_data["metadata"]["longAddress"],
                        "long_pubkey": contract_data["metadata"]["longPublicKey"],
                    }

                    settle_hedge_position_offer_serializer = SettleHedgePositionOfferSerializer(
                        data=settle_hedge_position_offer_data,
                        hedge_position_offer=instance,
                        auto_settled=True,
                    )
                    settle_hedge_position_offer_serializer.is_valid(raise_exception=True)
                    instance = settle_hedge_position_offer_serializer.save()

                    # TODO: resolve tx_hash and other funding details and save to instance.hedge_position
                    instance.hedge_position.funding_tx_hash = ""
                    instance.hedge_position.save()
                else:
                    raise Exception(f"Failed to find match in liduidity pool for {instance}")
            else:
                raise Exception(f"Failed to find match for {instance}")
        return instance 


class SettleHedgePositionOfferSerializer(serializers.Serializer):
    address = serializers.CharField()
    anyhedge_contract_version = serializers.CharField()
    oracle_pubkey = serializers.CharField()
    oracle_price = serializers.IntegerField()
    oracle_timestamp = serializers.IntegerField() # unix
    long_wallet_hash = serializers.CharField()
    long_address = serializers.CharField()
    long_pubkey = serializers.CharField()

    def __init__(self, *args, hedge_position_offer=None, auto_settled=False, **kwargs):
        self.hedge_position_offer = hedge_position_offer
        self.auto_settled = auto_settled
        return super().__init__(*args, **kwargs)

    def validate(self, data):
        assert isinstance(self.hedge_position_offer, HedgePositionOffer), \
            f"Expected type {HedgePositionOffer} but got {type(self.hedge_position_offer)}"

        if self.hedge_position_offer.status == HedgePositionOffer.STATUS_SETTLED:
            raise serializers.ValidationError("Hedge position offer is already settled")
        elif self.hedge_position_offer.status == HedgePositionOffer.STATUS_CANCELLED:
            raise serializers.ValidationError("Hedge position offer is already cancelled")
    
        if not match_pubkey_to_cash_address(data["long_pubkey"], data["long_address"]):
            raise serializers.ValidationError("public key & address does not match")

        return data

    @transaction.atomic()
    def save(self):
        validated_data = self.validated_data
        start_timestamp = datetime.fromtimestamp(validated_data["oracle_timestamp"]).replace(tzinfo=pytz.UTC)
        maturity_timestamp = start_timestamp + timedelta(seconds=self.hedge_position_offer.duration_seconds) 

        hedge_position = HedgePosition.objects.create(
            address = validated_data["address"],
            anyhedge_contract_version = validated_data["anyhedge_contract_version"],
            satoshis = self.hedge_position_offer.satoshis,
            start_timestamp = start_timestamp,
            maturity_timestamp = maturity_timestamp,
            hedge_wallet_hash = self.hedge_position_offer.wallet_hash,
            hedge_address = self.hedge_position_offer.hedge_address,
            hedge_pubkey = self.hedge_position_offer.hedge_pubkey,
            long_wallet_hash = validated_data["long_wallet_hash"],
            long_address = validated_data["long_address"],
            long_pubkey = validated_data["long_pubkey"],
            oracle_pubkey = validated_data["oracle_pubkey"],
            start_price = validated_data["oracle_price"],
            low_liquidation_multiplier = self.hedge_position_offer.low_liquidation_multiplier,
            high_liquidation_multiplier = self.hedge_position_offer.high_liquidation_multiplier,
        )

        self.hedge_position_offer.hedge_position = hedge_position
        self.hedge_position_offer.status = HedgePositionOffer.STATUS_SETTLED
        self.hedge_position_offer.auto_settled = self.auto_settled
        self.hedge_position_offer.save()

        if self.hedge_position_offer.hedge_funding_proposal:
            hedge_funding_proposal = self.hedge_position_offer.hedge_funding_proposal
            funding_proposal_data = {
                "hedge_address": hedge_position.address,
                "position": "hedge",
                "tx_hash": hedge_funding_proposal.tx_hash,
                "tx_index": hedge_funding_proposal.tx_index,
                "tx_value": hedge_funding_proposal.tx_value,
                "script_sig": hedge_funding_proposal.script_sig,
                "pubkey": hedge_funding_proposal.pubkey,
                "input_tx_hashes": hedge_funding_proposal.input_tx_hashes,
            }
            funding_proposal_serializer = FundingProposalSerializer(data=funding_proposal_data)
            funding_proposal_serializer.is_valid(raise_exception=True)
            funding_proposal_serializer.save()

        if self.auto_settled:
            consume_long_account_allowance(hedge_position.long_address, hedge_position.long_input_sats)

        send_settlement_update(self.hedge_position_offer)
        return self.hedge_position_offer
