import pytz
from datetime import datetime, timedelta
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from .conf import settings as app_settings
from .models import (
    HedgePosition,
    HedgePositionMetadata,
    HedgeSettlement,
    SettlementService,
    HedgePositionFee,
    HedgeFundingProposal,
    MutualRedemption,
    HedgePositionOffer,
    HedgePositionOfferCounterParty,
    HedgePositionFunding,

    Oracle,
    PriceOracleMessage,
)
from .utils.address import match_pubkey_to_cash_address
from .utils.contract import (
    create_contract,
    get_contract_status,
    compile_contract_from_hedge_position_offer,
)
from .utils.funding import (
    get_p2p_settlement_service_fee,
    get_tx_hash,
    calculate_funding_amounts,
    validate_funding_transaction,
    calculate_hedge_sats,
)
from .utils.liquidity import (
    find_matching_position_offer,
    find_close_matching_offer_suggestion,
    fund_hedge_position,
)
from .utils.price_oracle import (
    get_price_messages,
    save_price_oracle_message,
)
from .utils.validators import (
    ValidAddress,
    ValidTxHash,
)
from .utils.websocket import (
    send_offer_settlement_update,
    send_funding_tx_update,
    send_mutual_redemption_update,
    send_hedge_position_offer_update,
)
from .tasks import (
    validate_contract_funding,
    parse_contract_liquidity_fee,
)


class TimestampField(serializers.IntegerField):
    def to_representation(self, value):
        return datetime.timestamp(value)

    def to_internal_value(self, data):
        return datetime.fromtimestamp(data).replace(tzinfo=pytz.UTC)


class FundingProposalSerializer(serializers.Serializer):
    hedge_address = serializers.CharField(validators=[ValidAddress(addr_type=ValidAddress.TYPE_CASHADDR)])
    position = serializers.CharField() # hedge | long
    tx_hash = serializers.CharField(validators=[ValidTxHash()])
    tx_index = serializers.IntegerField()
    tx_value = serializers.IntegerField()
    script_sig = serializers.CharField()
    pubkey = serializers.CharField(required=False)
    input_tx_hashes = serializers.ListField(
        child=serializers.CharField(),
        required=False
    )

    def validate_hedge_address(self, value):
        try:
            hedge_position_obj = HedgePosition.objects.get(address=value)
            if hedge_position_obj.funding_tx_hash:
                raise serializers.ValidationError("Hedge position is already funded")
            try:
                if hedge_position_obj.settlement:
                    raise serializers.ValidationError("Hedge position is already settled")
            except HedgePosition.settlement.RelatedObjectDoesNotExist:
                pass

        except HedgePosition.DoesNotExist:
            raise serializers.ValidationError("Hedge position does not exist")

        return value

    def validate_position(self, value):
        if value != "hedge" and value != "long":
            raise serializers.ValidationError("Position must be \"hedge\" or \"long\"")
        return value

    @transaction.atomic()
    def create(self, validated_data):
        hedge_address = validated_data.pop("hedge_address")
        position = validated_data.pop("position")
        hedge_pos_obj = HedgePosition.objects.get(address=hedge_address)

        update_hedge_obj = True

        funding_proposal = HedgeFundingProposal()
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
        funding_proposal.input_tx_hashes = validated_data.get("input_tx_hashes", None)
        funding_proposal.save()

        if update_hedge_obj:
            if position == "hedge":
                hedge_pos_obj.hedge_funding_proposal = funding_proposal
            elif position == "long":
                hedge_pos_obj.long_funding_proposal = funding_proposal
            hedge_pos_obj.save()

        send_funding_tx_update(hedge_pos_obj, position=position)
        return funding_proposal


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


class HedgeSettlementSerializer(serializers.ModelSerializer):
    settlement_message_timestamp = TimestampField()

    class Meta:
        model = HedgeSettlement
        fields = [
            "spending_transaction",
            "settlement_type",
            "hedge_satoshis",
            "long_satoshis",
            "oracle_pubkey",
            "settlement_price",
            "settlement_price_sequence",
            "settlement_message_sequence",
            "settlement_message_timestamp",
        ]


class SettlementServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = SettlementService
        fields = [
            "domain",
            "scheme",
            "port",
            "hedge_signature",
            "long_signature",
            "auth_token",
        ]

    def validate(self, data):
        if not data.get("hedge_signature", None) and not data.get("long_signature", None):
            raise serializers.ValidationError("hedge_signature or long_signature must be given")
        return data


class HedgePositionFeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = HedgePositionFee
        fields = [
            "address",
            "satoshis",
        ]

class HedgePositionFundingSerializer(serializers.ModelSerializer):
    class Meta:
        model = HedgePositionFunding
        fields = [
            "tx_hash",
            "funding_output",
            "funding_satoshis",
            "fee_output",
            "fee_satoshis",
        ]


class MutualRedemptionSerializer(serializers.ModelSerializer):

    class Meta:
        model = MutualRedemption
        fields = [
            "redemption_type",
            "hedge_satoshis",
            "long_satoshis",
            "hedge_schnorr_sig",
            "long_schnorr_sig",
            "settlement_price",
            "tx_hash",
        ]

        extra_kwargs = {
            "tx_hash": {
                "read_only": True,
            },
        }

    def __init__(self, *args, hedge_position=None, **kwargs):
        self.hedge_position = hedge_position
        return super().__init__(*args, **kwargs)

    def validate_redemption_type(self, value):
        if self.instance and self.instance.redemption_type != value:
            raise serializers.ValidationError("Redemption type is not editable")
        return value

    def validate_hedge_satoshis(self, value):
        if self.instance and self.instance.hedge_satoshis != value:
            raise serializers.ValidationError("Hedge satoshis is not editable")
        return value

    def validate_long_satoshis(self, value):
        if self.instance and self.instance.long_satoshis != value:
            raise serializers.ValidationError("Long satoshis is not editable")
        return value

    def validate_settlement_price(self, value):
        if self.instance and self.instance.settlement_price != value:
            raise serializers.ValidationError("Settlement price is not editable")
        return value

    def validate(self, data):
        redemption_type = data.get("redemption_type", None)
        settlement_price = data.get("settlement_price", None)
        hedge_satoshis = data.get("hedge_satoshis", None)
        long_satoshis = data.get("long_satoshis", None)

        if not self.hedge_position.funding_tx_hash:
            raise serializers.ValidationError("Contract is not yet funded")

        if not self.hedge_position.funding:
            funding_validation = validate_contract_funding(self.hedge_position.address)
            if not funding_validation["success"] or not self.hedge_position.funding:
                raise serializers.ValidationError("Unable to verify funding transaction")

        if redemption_type == MutualRedemption.TYPE_EARLY_MATURATION:
            if not settlement_price and settlement_price <= 0:
                raise serializers.ValidationError(f"Settlement price required for type '{MutualRedemption.TYPE_EARLY_MATURATION}'")

        elif redemption_type == MutualRedemption.TYPE_REFUND:
            if abs(hedge_satoshis - self.hedge_position.satoshis) > 1:
                raise serializers.ValidationError(f"Hedge payout must be {self.hedge_position.satoshis} for type '{MutualRedemption.TYPE_REFUND}'")
            elif abs(long_satoshis - self.hedge_position.long_input_sats) > 1:
                raise serializers.ValidationError(f"Long payout must be {self.hedge_position.long_input_sats} for type '{MutualRedemption.TYPE_REFUND}'")

        # calculations from anyhedge library leaves 1175 for tx fee
        tx_fee = 1175
        expected_total_output = self.hedge_position.funding.funding_satoshis - tx_fee
        total_output = hedge_satoshis + long_satoshis
        if expected_total_output != total_output:
            raise serializers.ValidationError(f"Payout satoshis is not equal to {expected_total_output}")

        return data

    def create(self, validated_data):
        instance = MutualRedemption.objects.filter(hedge_position=self.hedge_position).first()

        if not instance:
            instance = MutualRedemption(hedge_position=self.hedge_position, **validated_data)

        if instance.long_satoshis != validated_data["long_satoshis"] or \
            instance.hedge_satoshis != validated_data["hedge_satoshis"] or \
            instance.redemption_type != validated_data["redemption_type"]:

            instance.hedge_schnorr_sig = None
            instance.long_schnorr_sig = None

        instance.long_satoshis = validated_data["long_satoshis"]
        instance.hedge_satoshis = validated_data["hedge_satoshis"]
        instance.redemption_type = validated_data["redemption_type"]
        instance.settlement_price = validated_data.get("settlement_price", None)

        if validated_data.get("hedge_schnorr_sig", None):
            instance.hedge_schnorr_sig = validated_data["hedge_schnorr_sig"]

        if validated_data.get("long_schnorr_sig", None):
            instance.long_schnorr_sig = validated_data["long_schnorr_sig"]

        instance.save()
        send_mutual_redemption_update(instance, action="created")
        return instance

class HedgePositionMetadataSerializer(serializers.ModelSerializer):
    class Meta:
        model = HedgePositionMetadata
        fields = [
            "position_taker",
            "liquidity_fee",
            "network_fee",
            "total_hedge_funding_sats",
            "total_long_funding_sats",
        ]

class HedgePositionSerializer(serializers.ModelSerializer):
    hedge_funding_proposal = HedgeFundingProposalSerializer(required=False)
    long_funding_proposal = HedgeFundingProposalSerializer(required=False)
    start_timestamp = TimestampField()
    maturity_timestamp = TimestampField()

    settlement = HedgeSettlementSerializer(read_only=True)
    settlement_service = SettlementServiceSerializer()
    check_settlement_service = serializers.BooleanField(default=True, required=False, write_only=True)
    fee = HedgePositionFeeSerializer()
    funding = HedgePositionFundingSerializer(read_only=True)
    mutual_redemption = MutualRedemptionSerializer(read_only=True)
    metadata = HedgePositionMetadataSerializer()

    class Meta:
        model = HedgePosition
        fields = [
            "id",
            "address",
            "anyhedge_contract_version",
            "satoshis",
            "start_timestamp",
            "maturity_timestamp",
            "hedge_wallet_hash",
            "hedge_address",
            "hedge_pubkey",
            "hedge_address_path",
            "long_wallet_hash",
            "long_address",
            "long_pubkey",
            "long_address_path",
            "oracle_pubkey",
            "start_price",
            "low_liquidation_multiplier",
            "high_liquidation_multiplier",
            "funding_tx_hash",
            "funding_tx_hash_validated",
            "hedge_funding_proposal",
            "long_funding_proposal",

            "settlement",
            "settlement_service",
            "check_settlement_service",
            "fee",
            "funding",
            "mutual_redemption",
            "metadata",
        ]
        extra_kwargs = {
            "address": {
                "validators": [ValidAddress(addr_type=ValidAddress.TYPE_CASHADDR)]
            },
            "hedge_address": {
                "validators": [ValidAddress(addr_type=ValidAddress.TYPE_CASHADDR)]
            },
            "long_address": {
                "validators": [ValidAddress(addr_type=ValidAddress.TYPE_CASHADDR)]
            },
            "hedge_wallet_hash": {
                "allow_blank": True
            },
            "long_wallet_hash": {
                "allow_blank": True
            },
            "funding_tx_hash": {
                "allow_blank": True
            },
            "funding_tx_hash_validated": {
                "read_only": True
            },
        }

    def validate(self, data):
        contract_address = data.get("address", None)
        oracle_pubkey = data.get("oracle_pubkey", None)
        settlement_service = data.get("settlement_service", None)
        check_settlement_service = data.get("check_settlement_service", None)
        hedge_pubkey = data.get("hedge_pubkey", None)
        long_pubkey = data.get("long_pubkey")

        if not match_pubkey_to_cash_address(data["hedge_pubkey"], data["hedge_address"]):
            raise serializers.ValidationError("hedge public key & address does not match")

        if not match_pubkey_to_cash_address(data["long_pubkey"], data["long_address"]):
            raise serializers.ValidationError("long public key & address does not match")

        if settlement_service and check_settlement_service:
            access_pubkey = ""
            access_signature = ""
            if settlement_service.get("hedge_signature", None):
                access_signature = settlement_service["hedge_signature"]
                access_pubkey = hedge_pubkey
            elif settlement_service.get("long_signature", None):
                access_signature = settlement_service["long_signature"]
                access_pubkey = long_pubkey
            contract_data = get_contract_status(
                contract_address,
                access_pubkey,
                access_signature,
                settlement_service_scheme=settlement_service["scheme"],
                settlement_service_domain=settlement_service["domain"],
                settlement_service_port=settlement_service["port"],
                authentication_token=settlement_service.get("auth_token", None),
            )
            if not contract_data or contract_data.get("address", None) != contract_address:
                raise serializers.ValidationError("Unable to verify contract from external settlement service")
        elif not settlement_service:
            if not Oracle.objects.filter(pubkey=oracle_pubkey).exists():
                raise serializers.ValidationError("Unknown 'oracle_pubkey', must provide settlement service")

        return data

    @transaction.atomic()
    def create(self, validated_data):
        validated_data.pop("check_settlement_service", None)
        settlement_service_data = validated_data.pop("settlement_service", None)
        fee_data = validated_data.pop("fee", None)
        hedge_funding_proposal_data = validated_data.pop("hedge_funding_proposal", None)
        long_funding_proposal_data = validated_data.pop("long_funding_proposal", None)
        metadata_data = validated_data.pop("metadata", None)

        instance = super().create(validated_data)
        save_instance = False

        if settlement_service_data is not None:
            settlement_service_data["hedge_position"] = instance
            SettlementService.objects.create(**settlement_service_data)
        
        if fee_data is not None:
            fee_data["hedge_position"] = instance
            HedgePositionFee.objects.create(**fee_data)

        if hedge_funding_proposal_data is not None:
            hedge_funding_proposal = HedgeFundingProposal.objects.create(**hedge_funding_proposal_data)
            instance.hedge_funding_proposal = hedge_funding_proposal
            save_instance = True

        if long_funding_proposal_data is not None:
            long_funding_proposal = HedgeFundingProposal.objects.create(**long_funding_proposal_data)
            instance.long_funding_proposal = long_funding_proposal
            save_instance = True

        if metadata_data is not None:
            metadata_data["hedge_position"] = instance 
            HedgePositionMetadata.objects.create(**metadata_data)

        if save_instance:
            instance.save()

        return instance


class HedgePositionOfferCounterPartySerializer(serializers.ModelSerializer):
    calculated_hedge_sats = serializers.SerializerMethodField()
    class Meta:
        model = HedgePositionOfferCounterParty
        fields = [
            "settlement_deadline",
            "contract_address",
            "anyhedge_contract_version",
            "wallet_hash",
            "address",
            "pubkey",
            "address_path",
            "price_message_timestamp",
            "price_value",
            "oracle_message_sequence",
            "settlement_service_fee",
            "settlement_service_fee_address",
            "calculated_hedge_sats",
        ]

        extra_kwargs = {
            "contract_address": {
                "read_only": True,
            },
            "anyhedge_contract_version": {
                "read_only": True,
            },
            "price_message_timestamp": {
                "read_only": True,
            },
            "price_value": {
                "read_only": True,
            },
            "settlement_deadline": {
                "read_only": True,
            },
            "settlement_service_fee": {
                "read_only": True,
            },
            "settlement_service_fee_address": {
                "read_only": True,
            },
            "oracle_message_sequence": {
                "required": False,
            },
        }

    def __init__(self, *args, hedge_position_offer=None, **kwargs):
        self.hedge_position_offer = hedge_position_offer
        super().__init__(*args, **kwargs)

    def get_calculated_hedge_sats(self, obj):
        if obj.hedge_position_offer.position == HedgePositionOffer.POSITION_LONG:
            return calculate_hedge_sats(
                long_sats=obj.hedge_position_offer.satoshis,
                low_price_mult=obj.hedge_position_offer.low_liquidation_multiplier,
                price_value=obj.price_value,
            )
        

    def validate_hedge_position_offer_id(self, value):
        try:
            hedge_position_offer = HedgePositionOffer.objects.get(id=value)
            if hedge_position_offer.status != HedgePositionOffer.STATUS_PENDING:
                raise serializers.ValidationError("hedge position offer is no longer active")
        except HedgePositionOffer.DoesNotExist:
            raise serializers.ValidationError("hedge position offer not found")

        return value

    def validate(self, data):
        if not isinstance(self.hedge_position_offer, HedgePositionOffer):
            raise serializers.ValidationError("invalid hedge position offer")

        if self.hedge_position_offer.status != HedgePositionOffer.STATUS_PENDING:
            raise serializers.ValidationError("hedge position offer is no longer active")

        if not match_pubkey_to_cash_address(data["pubkey"], data["address"]):
            raise serializers.ValidationError("public key & address does not match")
        return data

    @transaction.atomic()
    def create(self, validated_data):
        validated_data["hedge_position_offer"] = self.hedge_position_offer

        # get latest price data or price data from oracle_message_sequence
        oracle_message_sequence = validated_data.pop("oracle_message_sequence", None)
        price_oracle_message = self.get_price_message(
            self.hedge_position_offer.oracle_pubkey,
            oracle_message_sequence=oracle_message_sequence,
        )

        # construct contract from js scripts to get address & anyhedge_contract_version
        contract_creation_params = {
            "low_price_multiplier": self.hedge_position_offer.low_liquidation_multiplier,
            "high_price_multiplier": self.hedge_position_offer.high_liquidation_multiplier,
            "duration_seconds": self.hedge_position_offer.duration_seconds,
            "oracle_pubkey": self.hedge_position_offer.oracle_pubkey,
            "price_oracle_message_sequence": price_oracle_message.message_sequence,
        }
        if self.hedge_position_offer.position == HedgePositionOffer.POSITION_HEDGE:
            contract_creation_params["satoshis"] = self.hedge_position_offer.satoshis
            contract_creation_params["hedge_address"] = self.hedge_position_offer.address
            contract_creation_params["hedge_pubkey"] = self.hedge_position_offer.pubkey
            contract_creation_params["short_address"] = validated_data["address"]
            contract_creation_params["short_pubkey"] = validated_data["pubkey"]
        else:
            calculated_hedge_sats = calculate_hedge_sats(
                long_sats=self.hedge_position_offer.satoshis,
                low_price_mult=self.hedge_position_offer.low_liquidation_multiplier,
                price_value=price_oracle_message.price_value,
            )
            contract_creation_params["satoshis"] = calculated_hedge_sats
            contract_creation_params["hedge_address"] = validated_data["address"]
            contract_creation_params["hedge_pubkey"] = validated_data["pubkey"]
            contract_creation_params["short_address"] = self.hedge_position_offer.address
            contract_creation_params["short_pubkey"] = self.hedge_position_offer.pubkey

        create_contract_response = create_contract(**contract_creation_params)
        if not create_contract_response.get("success", None):
            raise serializers.ValidationError("unable to construct contract")
        contract_data = create_contract_response["contractData"]

        validated_data["contract_address"] = contract_data["address"]
        validated_data["anyhedge_contract_version"] = contract_data["version"]
        validated_data["price_message_timestamp"] = price_oracle_message.message_timestamp
        validated_data["price_value"] = price_oracle_message.price_value
        validated_data["settlement_deadline"] = timezone.now() + timedelta(minutes=15)
        validated_data["oracle_message_sequence"] = price_oracle_message.message_sequence

        settlement_service_fee = get_p2p_settlement_service_fee()
        if settlement_service_fee and "satoshis" in settlement_service_fee and "address" in settlement_service_fee:
            validated_data["settlement_service_fee"] = settlement_service_fee["satoshis"]
            validated_data["settlement_service_fee_address"] = settlement_service_fee["address"]

        instance = super().create(validated_data)
        instance.hedge_position_offer.status = HedgePositionOffer.STATUS_ACCEPTED
        instance.hedge_position_offer.save()

        send_hedge_position_offer_update(
            instance.hedge_position_offer,
            action="accepted",
            metadata={ "accepting_wallet_hash": instance.wallet_hash }
        )
        return instance

    def get_price_message(self, oracle_pubkey, oracle_message_sequence=None):
        now = timezone.now()
        query_kwargs = {
            "pubkey": oracle_pubkey,
        }
        if oracle_message_sequence:
            query_kwargs["message_sequence"] = oracle_message_sequence
        else:
            query_kwargs["message_timestamp__gte"] = now - timedelta(seconds=60)

        price_oracle_message = PriceOracleMessage.objects.filter(**query_kwargs).order_by("-message_timestamp").first()

        if not price_oracle_message:
            query_kwargs = { "count": 1 }
            oracle_obj = Oracle.objects.filter(pubkey=oracle_pubkey).first()
            if oracle_obj:
                query_kwargs["relay"] = oracle_obj.relay
                query_kwargs["port"] = oracle_obj.port

            if oracle_message_sequence:
                query_kwargs["min_message_sequence"] = oracle_message_sequence
                query_kwargs["max_message_sequence"] = oracle_message_sequence
            price_data = get_price_messages(oracle_pubkey, **query_kwargs)
            if len(price_data):
                price_oracle_message = save_price_oracle_message(oracle_pubkey, price_data[0])

        if not price_oracle_message:
            raise serializers.ValidationError("unable to resolve oracle price")
        elif price_oracle_message.message_timestamp < now - timedelta(seconds=120):
            raise serializers.ValidationError("starting price is outdated")
        return price_oracle_message


class HedgePositionOfferSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)
    hedge_position = HedgePositionSerializer(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    counter_party_info = HedgePositionOfferCounterPartySerializer(read_only=True)

    class Meta:
        model = HedgePositionOffer
        fields = [
            "id",
            "status",
            "position",
            "wallet_hash",
            "satoshis",
            "duration_seconds",
            "high_liquidation_multiplier",
            "low_liquidation_multiplier",
            "oracle_pubkey",
            "address",
            "pubkey",
            "address_path",
            "expires_at",
            "created_at",
            "hedge_position",
            "counter_party_info",
        ]

        extra_kwargs = {
            "position": {
                "required": True,
                "allow_blank": False,
            },
        }

    def validate_wallet_hash(self, value):
        if self.instance and self.instance.wallet_hash != value:
            raise serializers.ValidationError("wallet_hash is not editable")
        return value

    def validate(self, data):
        if self.instance and self.instance.status != HedgePositionOffer.STATUS_PENDING:
            raise serializers.ValidationError(f"unable to edit in \"{self.instance.status}\" state")
        if self.instance:
            pubkey = data.get("pubkey", self.instance.pubkey)
            address = data.get("address", self.instance.address)
        else:
            pubkey = data["pubkey"]
            address = data["address"]
        if not match_pubkey_to_cash_address(pubkey, address):
            raise serializers.ValidationError("public key & address does not match")
        return data


class MatchHedgePositionSerializer(serializers.Serializer):
    wallet_hash = serializers.CharField(required=False)
    position = serializers.CharField()
    satoshis = serializers.IntegerField()
    duration_seconds = serializers.IntegerField()
    low_liquidation_multiplier = serializers.FloatField()
    high_liquidation_multiplier = serializers.FloatField()
    oracle_pubkey = serializers.CharField()

    similarity = serializers.FloatField(required=False, default=0.5)

    matching_position_offer = HedgePositionOfferSerializer(read_only=True)
    similar_position_offers = HedgePositionOfferSerializer(many=True, read_only=True)

    def validate_position(self, value):
        if value not in [HedgePositionOffer.POSITION_HEDGE, HedgePositionOffer.POSITION_LONG]:
            raise serializers.ValidationError("invalid position type")
        return value

    def find_match(self):
        response = { **self.validated_data }
        response["matching_position_offer"] = find_matching_position_offer(
            position=self.validated_data["position"],
            amount=self.validated_data["satoshis"],
            duration_seconds=self.validated_data["duration_seconds"],
            low_liquidation_multiplier=self.validated_data["low_liquidation_multiplier"],
            high_liquidation_multiplier=self.validated_data["high_liquidation_multiplier"],
            exclude_wallet_hash=self.validated_data["wallet_hash"],
            oracle_pubkey=self.validated_data["oracle_pubkey"],
        )

        response["similar_position_offers"] = []
        if not response["matching_position_offer"]:
            response["similar_position_offers"] = find_close_matching_offer_suggestion(
                position=self.validated_data["position"],
                amount=self.validated_data["satoshis"],
                duration_seconds=self.validated_data["duration_seconds"],
                low_liquidation_multiplier=self.validated_data["low_liquidation_multiplier"],
                high_liquidation_multiplier=self.validated_data["high_liquidation_multiplier"],
                exclude_wallet_hash=self.validated_data["wallet_hash"],
                oracle_pubkey=self.validated_data["oracle_pubkey"],
                similarity=self.validated_data.get("similarity", 0.5),
            )

        return response


class SettleHedgePositionOfferSerializer(serializers.Serializer):
    counter_party_funding_proposal = HedgeFundingProposalSerializer()

    def __init__(self, *args, hedge_position_offer=None, **kwargs):
        self.hedge_position_offer = hedge_position_offer
        super().__init__(*args, **kwargs)

    def validate(self, data):
        if not isinstance(self.hedge_position_offer, HedgePositionOffer):
            raise serializers.ValidationError("invalid hedge position offer")

        if self.hedge_position_offer.status != HedgePositionOffer.STATUS_ACCEPTED:
            raise serializers.ValidationError("hedge position offer has not been accepted yet")

        try:
            if not self.hedge_position_offer.counter_party_info:
                raise HedgePositionOffer.counter_party_info.RelatedObjectDoesNotExist
        except HedgePositionOffer.counter_party_info.RelatedObjectDoesNotExist:
            raise serializers.ValidationError("counter party info missing")

        contract_data = compile_contract_from_hedge_position_offer(self.hedge_position_offer)
        funding_amounts = calculate_funding_amounts(contract_data, position=self.hedge_position_offer.position)

        counter_party_funding_proposal_data = data["counter_party_funding_proposal"]
        funding_amount = counter_party_funding_proposal_data["tx_value"]
        expected_amount = funding_amounts["long" if self.hedge_position_offer.position == HedgePositionOffer.POSITION_HEDGE else "hedge"]
        if funding_amount != expected_amount:
            raise serializers.ValidationError(f"invalid funding amount, expected {expected_amount} satoshis")

        return data

    @transaction.atomic()
    def save(self):
        validated_data = self.validated_data

        # create hedge position instance
        contract_data = compile_contract_from_hedge_position_offer(self.hedge_position_offer)
        contract_metadata = contract_data["metadata"]
        start_timestamp = self.hedge_position_offer.counter_party_info.price_message_timestamp
        maturity_timestamp = start_timestamp + timedelta(seconds=self.hedge_position_offer.duration_seconds)

        hedge_position = HedgePosition.objects.create(
            address = contract_data["address"],
            anyhedge_contract_version = contract_data["version"],
            satoshis = contract_metadata["hedgeInputSats"],
            start_timestamp = start_timestamp,
            maturity_timestamp = maturity_timestamp,
            hedge_address = contract_metadata["hedgeAddress"],
            hedge_pubkey = contract_metadata["hedgePublicKey"],
            long_address = contract_metadata["longAddress"],
            long_pubkey = contract_metadata["longPublicKey"],
            oracle_pubkey = contract_metadata["oraclePublicKey"],
            start_price = contract_metadata["startPrice"],
            low_liquidation_multiplier = contract_metadata["lowLiquidationPriceMultiplier"],
            high_liquidation_multiplier = contract_metadata["highLiquidationPriceMultiplier"],
        )
        hedge_position.hedge_wallet_hash = self.hedge_position_offer.wallet_hash
        hedge_position.hedge_address_path = self.hedge_position_offer.address_path
        hedge_position.long_wallet_hash = self.hedge_position_offer.counter_party_info.wallet_hash
        hedge_position.long_address_path = self.hedge_position_offer.counter_party_info.address_path
        if self.hedge_position_offer.position == HedgePositionOffer.POSITION_LONG:
            hedge_position.hedge_wallet_hash, hedge_position.long_wallet_hash = hedge_position.long_wallet_hash, hedge_position.hedge_wallet_hash
            hedge_position.hedge_address_path, hedge_position.long_address_path = hedge_position.long_address_path, hedge_position.hedge_address_path

        # create funding proposal of counter party
        counter_party_funding_proposal_data = validated_data["counter_party_funding_proposal"]
        counter_party_funding_proposal_obj = HedgeFundingProposal.objects.create(**counter_party_funding_proposal_data)
        if self.hedge_position_offer.position == HedgePositionOffer.POSITION_HEDGE:
            hedge_position.long_funding_proposal = counter_party_funding_proposal_obj
        else:
            hedge_position.hedge_funding_proposal = counter_party_funding_proposal_obj
        hedge_position.save()

        # create hedge position's fee, if available
        settlement_service_fee = self.hedge_position_offer.counter_party_info.settlement_service_fee
        settlement_service_fee_address = self.hedge_position_offer.counter_party_info.settlement_service_fee_address
        if settlement_service_fee and settlement_service_fee_address:
            HedgePositionFee.objects.create(
                hedge_position=hedge_position,
                satoshis=settlement_service_fee,
                address=settlement_service_fee_address,
            )

        # create hedge position's metadata
        HedgePositionMetadata.objects.create(
            hedge_position=hedge_position,
            position_taker=self.hedge_position_offer.position,
            liquidity_fee=0,
        )

        hedge_position.refresh_from_db()
        self.hedge_position_offer.hedge_position = hedge_position
        self.hedge_position_offer.status = HedgePositionOffer.STATUS_SETTLED
        self.hedge_position_offer.save()
        send_hedge_position_offer_update(
            self.hedge_position_offer,
            action="settled",
            metadata={
                "address": self.hedge_position_offer.hedge_position.address,
            }
        )
        return hedge_position


class SubmitFundingTransactionSerializer(serializers.Serializer):
    hedge_position_address = serializers.CharField(validators=[ValidAddress(addr_type=ValidAddress.TYPE_CASHADDR)])
    tx_hash = serializers.CharField(validators=[ValidTxHash()], required=False)
    tx_hex = serializers.CharField(required=False)

    def validate_hedge_address(value):
        try:
            hedge_position_obj = HedgePosition.objects.get(address=value)
        except HedgePosition.DoesNotExist:
            raise serializers.ValidationError("Hedge position does not exist")

        return value

    def validate(self, data):
        hedge_position_address = data.get("hedge_position_address", None)
        tx_hash = data.get("tx_hash", None)
        tx_hex = data.get("tx_hex", None)
        if not tx_hash and not tx_hex:
            raise serializers.ValidationError("tx_hash or tx_hex required")

        # TODO: route for broadcasting tx_hex if necessary
        if tx_hash:
            funding_tx_validation = validate_funding_transaction(tx_hash, hedge_position_address)
            if not funding_tx_validation["valid"]:
                raise serializers.ValidationError(f"funding tx hash '{tx_hash}' invalid")
        elif tx_hex:
            _tx_hash = get_tx_hash(tx_hex)
            funding_tx_validation = validate_funding_transaction(_tx_hash, hedge_position_address)
            if not funding_tx_validation["valid"]:
                raise serializers.ValidationError(f"funding tx hex invalid")

        return data
    
    @transaction.atomic()
    def save(self):
        validated_data = self.validated_data
        hedge_position_address = validated_data["hedge_position_address"]

        tx_hash = validated_data.get("tx_hash", None)
        if not tx_hash:
            tx_hash = get_tx_hash(validated_data["tx_hex"])

        hedge_position_obj = HedgePosition.objects.get(address=hedge_position_address)

        if hedge_position_obj.funding_tx_hash != tx_hash:
            hedge_position_obj.funding_tx_hash_validated = False

        hedge_position_obj.funding_tx_hash = tx_hash
        hedge_position_obj.save()
        send_funding_tx_update(hedge_position_obj, tx_hash=hedge_position_obj.funding_tx_hash)
        return hedge_position_obj


class FundGeneralProcotolLPContractSerializer(serializers.Serializer):
    contract_address = serializers.CharField()
    position = serializers.ChoiceField(choices=["hedge", "long"])
    hedge_wallet_hash = serializers.CharField(required=False)
    hedge_pubkey = serializers.CharField(required=False)
    hedge_address_path = serializers.CharField(required=False)

    long_wallet_hash = serializers.CharField(required=False)
    long_pubkey = serializers.CharField(required=False)
    long_address_path = serializers.CharField(required=False)
    oracle_message_sequence = serializers.IntegerField()
    liquidity_fee = serializers.IntegerField(required=False)

    settlement_service = SettlementServiceSerializer() # do i need this here or js script will provide ?
    funding_proposal = HedgeFundingProposalSerializer()

    def validate(self, data):
        position = data["position"]
        hedge_wallet_hash = data.get("hedge_wallet_hash", None)
        hedge_pubkey = data.get("hedge_pubkey", None)
        long_wallet_hash = data.get("long_wallet_hash", None)
        long_pubkey = data.get("long_pubkey", None)

        if position == "hedge" and (not hedge_wallet_hash or not hedge_pubkey):
            raise serializers.ValidationError("'hedge_wallet_hash' or 'hedge_pubkey' required when taking 'hedge' position")

        if position == "long" and (not long_wallet_hash or not long_pubkey):
            raise serializers.ValidationError("'long_wallet_hash' or 'long_pubkey' required when taking 'long' position")

        return data

    @transaction.atomic()
    def save(self):
        validated_data = self.validated_data
        contract_address = validated_data["contract_address"]
        position = validated_data["position"]
        hedge_wallet_hash = validated_data.get("hedge_wallet_hash", None)
        hedge_pubkey = validated_data.get("hedge_pubkey", None)
        hedge_address_path = validated_data.get("hedge_address_path", None)
        long_wallet_hash = validated_data.get("long_wallet_hash", None)
        long_pubkey = validated_data.get("long_pubkey", None)
        long_address_path = validated_data.get("long_address_path", None)

        oracle_message_sequence = validated_data["oracle_message_sequence"]
        liquidity_fee = validated_data.get("liquidity_fee", None)
        settlement_service = validated_data["settlement_service"]
        funding_proposal = validated_data["funding_proposal"]

        access_pubkey = ""
        access_signature = ""
        if settlement_service.get("hedge_signature", None):
            access_signature = settlement_service["hedge_signature"]
            access_pubkey = hedge_pubkey
        elif settlement_service.get("long_signature", None):
            access_signature = settlement_service["long_signature"]
            access_pubkey = long_pubkey

        contract_data = get_contract_status(
            contract_address,
            access_pubkey,
            access_signature,
            settlement_service_scheme=settlement_service["scheme"],
            settlement_service_domain=settlement_service["domain"],
            settlement_service_port=settlement_service["port"],
            authentication_token=settlement_service.get("auth_token", None),
        )

        if contract_data["address"] != contract_address:
            raise serializers.ValidationError("Contract address from settlement does not match")

        contract_metadata = contract_data["metadata"]
        start_timestamp = contract_metadata["startTimestamp"]
        maturity_timestamp = start_timestamp + contract_metadata["duration"]

        hedge_position_data = {
            "address": contract_data["address"],
            "anyhedge_contract_version": contract_data["version"],
            "satoshis": contract_metadata["hedgeInputSats"],
            "start_timestamp": contract_metadata["startTimestamp"],
            "maturity_timestamp": maturity_timestamp,
            "hedge_wallet_hash": hedge_wallet_hash or "",
            "hedge_address": contract_metadata["hedgeAddress"],
            "hedge_address_path": hedge_address_path,
            "hedge_pubkey": contract_metadata["hedgePublicKey"],
            "long_wallet_hash": long_wallet_hash or "",
            "long_address": contract_metadata["longAddress"],
            "long_address_path": long_address_path,
            "long_pubkey": contract_metadata["longPublicKey"],
            "oracle_pubkey": contract_metadata["oraclePublicKey"],
            "start_price": contract_metadata["startPrice"],
            "low_liquidation_multiplier": contract_metadata["lowLiquidationPriceMultiplier"],
            "high_liquidation_multiplier": contract_metadata["highLiquidationPriceMultiplier"],
            "funding_tx_hash": "",
            "settlement_service": settlement_service,
            "check_settlement_service": False,
            "metadata": {
                "position_taker": position,
            },
        }

        if position == "hedge":
            validated_data["hedge_funding_proposal"] = funding_proposal
            hedge_position_data["metadata"]["total_hedge_funding_sats"] = funding_proposal["tx_value"]
        elif position == "long":
            validated_data["long_funding_proposal"] = funding_proposal
            hedge_position_data["metadata"]["total_long_funding_sats"] = funding_proposal["tx_value"]

        if contract_data.get("fee", None):
            hedge_position_data["fee"] = {
                "address": contract_data["fee"]["address"],
                "satoshis": contract_data["fee"]["satoshis"],
            }

        if liquidity_fee is not None:
            hedge_position_data["metadata"]["liquidity_fee"] = liquidity_fee

        hedge_position_serializer = HedgePositionSerializer(data=hedge_position_data)
        hedge_position_serializer.is_valid(raise_exception=True)
        hedge_position_obj = hedge_position_serializer.save()

        # this must be at the last part as much as possible
        funding_response = fund_hedge_position(
            contract_data,
            {
                "txHash": funding_proposal["tx_hash"],
                "txIndex": funding_proposal["tx_index"],
                "txValue": funding_proposal["tx_value"],
                "scriptSig": funding_proposal["script_sig"],
                "publicKey": funding_proposal["pubkey"],
                "inputTxHashes": funding_proposal["input_tx_hashes"],
            },
            oracle_message_sequence,
            position=position,
        )
        if not funding_response["success"]:
            error = "Error in funding hedge position"
            if funding_response.get("error", None):
                error += f". {funding_response['error']}"
            raise serializers.ValidationError(error)

        hedge_position_obj.funding_tx_hash = funding_response["fundingTransactionHash"]
        hedge_position_obj.save()

        parse_contract_liquidity_fee.delay(hedge_position_obj.address, hard_update=False)
        return hedge_position_obj


class OracleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Oracle
        fields = [
            "pubkey",
            "asset_name",
            "asset_currency",
            "asset_decimals",
        ]

class PriceOracleMessageSerializer(serializers.ModelSerializer):
    message_timestamp = TimestampField()

    class Meta:
        model = PriceOracleMessage
        fields = [
            "pubkey",
            "message_timestamp",
            "price_value",
            "price_sequence",
            "message_sequence",
        ]
