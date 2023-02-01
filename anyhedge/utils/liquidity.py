import json
import requests
import logging
from urllib.parse import urljoin
from django.utils import timezone
from django.db import transaction
from django.db.models import OuterRef, Subquery, Sum, F, Value, Q
from django.db.models.functions import Coalesce, Greatest, Abs
from ..conf import settings as app_settings
from ..js.runner import AnyhedgeFunctions
from ..models import (
    HedgePositionFunding,
    HedgePositionMetadata,
    HedgePositionOffer,
    HedgePositionOfferCounterParty,
)
from .api import get_bchd_instance
from .websocket import send_long_account_update

LOGGER = logging.getLogger("main")

@transaction.atomic()
def update_hedge_position_offer_deadline():
    hedge_position_offers = HedgePositionOffer.objects.filter(
        status=HedgePositionOffer.STATUS_ACCEPTED,
        counter_party_info__settlement_deadline__lte=timezone.now(),
    )

    if not hedge_position_offers.count():
        return

    HedgePositionOfferCounterParty.objects.filter(hedge_position_offer__in=hedge_position_offers).delete()
    return hedge_position_offers.update(status=HedgePositionOffer.STATUS_PENDING)


def find_matching_position_offer(
    position="",
    amount=0,
    duration_seconds=0,
    low_liquidation_multiplier=0.9,
    high_liquidation_multiplier=10,
    exclude_wallet_hash="",
    oracle_pubkey="",
):
    update_hedge_position_offer_deadline()
    now = timezone.now()
    _position = HedgePositionOffer.POSITION_HEDGE
    if position == HedgePositionOffer.POSITION_HEDGE:
        _position = HedgePositionOffer.POSITION_LONG

    if position == HedgePositionOffer.POSITION_HEDGE:
        counter_party_sats = amount * (1/low_liquidation_multiplier - 1) # calculating long sats
    else:
        counter_party_sats = amount / (1/low_liquidation_multiplier - 1) # calculating hedge sats

    # due to missing price value, there is an error in the actual sats
    # we filter a range instead of filtering the exact sats using the value below
    sats_range = 10 ** 4

    queryset = HedgePositionOffer.objects.filter(
        Q(expires_at__isnull=True) | Q(expires_at__gte=now),
        position=_position,
        status=HedgePositionOffer.STATUS_PENDING,
        satoshis__gte = counter_party_sats - sats_range,
        satoshis__lte = counter_party_sats + sats_range,
        duration_seconds=duration_seconds,
        low_liquidation_multiplier=low_liquidation_multiplier,
        high_liquidation_multiplier=high_liquidation_multiplier,
        oracle_pubkey=oracle_pubkey,
    )
    if exclude_wallet_hash:
        queryset = queryset.exclude(wallet_hash=exclude_wallet_hash)

    queryset = queryset.annotate(
        sats_diff = Abs(F("satoshis") - Value(counter_party_sats))
    ).order_by("sats_diff", "created_at")

    return queryset.first()


def find_close_matching_offer_suggestion(
    position="",
    amount=0,
    duration_seconds=0,
    low_liquidation_multiplier=0.9,
    high_liquidation_multiplier=10,
    exclude_wallet_hash="",
    oracle_pubkey="",
    similarity=0.5, # a common value to be used as multipler for filter range value value between 0 to 1
):
    update_hedge_position_offer_deadline()
    now = timezone.now()
    _position = HedgePositionOffer.POSITION_HEDGE
    if position == HedgePositionOffer.POSITION_HEDGE:
        _position = HedgePositionOffer.POSITION_LONG

    # ranges are 2 length arrays representing min & max, respectively
    low_liquidation_multiplier_range = [low_liquidation_multiplier*(similarity), low_liquidation_multiplier*(2 - similarity)]
    high_liquidation_multiplier_range = [high_liquidation_multiplier*(similarity), high_liquidation_multiplier*(2 - similarity)]
    duration_seconds_range = [duration_seconds*(similarity), duration_seconds*(2-similarity)]

    if position == HedgePositionOffer.POSITION_HEDGE:
        counter_party_sats = amount * (1/low_liquidation_multiplier - 1) # calculating long sats
        counter_party_sats_range = [counter_party_sats*(similarity), counter_party_sats*(2-similarity)]
    else:
        counter_party_sats = amount / (1/low_liquidation_multiplier - 1) # calculating hedge sats
        counter_party_sats_range = [counter_party_sats*(similarity), counter_party_sats*(2-similarity)]

    # LOGGER.info(
    #     f"find_close_matching_offer_suggestion({position}):\n" \
    #     f"\tamount={amount}\n" \
    #     f"\tduration_seconds={duration_seconds}\n" \
    #     f"\tlow_liquidation_multiplier={low_liquidation_multiplier}\n" \
    #     f"\thigh_liquidation_multiplier={high_liquidation_multiplier}\n" \
    #     f"\texclude_wallet_hash={exclude_wallet_hash}\n" \
    #     f"\toracle_pubkey={oracle_pubkey}\n" \
    #     f"\tsimilarity={similarity}\n" \
    #     f"\tlow_liquidation_multiplier_range={low_liquidation_multiplier_range}\n" \
    #     f"\thigh_liquidation_multiplier_range={high_liquidation_multiplier_range}\n" \
    #     f"\tduration_seconds_range={duration_seconds_range}\n" \
    #     f"\tcounter_party_sats_range={counter_party_sats_range}\n"
    # )

    # filter offers by a range of value
    queryset = HedgePositionOffer.objects.filter(
        Q(expires_at__isnull=True) | Q(expires_at__gte=now),
        position=_position,
        status=HedgePositionOffer.STATUS_PENDING,
        oracle_pubkey=oracle_pubkey,
        satoshis__gte = counter_party_sats_range[0],
        satoshis__lte = counter_party_sats_range[1],
        duration_seconds__gte=duration_seconds_range[0],
        duration_seconds__lte=duration_seconds_range[1],
        high_liquidation_multiplier__gte=high_liquidation_multiplier_range[0],
        high_liquidation_multiplier__lte=high_liquidation_multiplier_range[1],
        low_liquidation_multiplier__gte=low_liquidation_multiplier_range[0],
        low_liquidation_multiplier__lte=low_liquidation_multiplier_range[1],
    )

    if exclude_wallet_hash:
        queryset = queryset.exclude(wallet_hash=exclude_wallet_hash)

    # order offers by their similarity
    queryset = queryset.annotate(
        sats_diff = Abs(F("satoshis")/Value(counter_party_sats)),
        duration_diff = Abs(F("duration_seconds")/Value(duration_seconds)),
    ).annotate(
        diff = F("sats_diff")*Value(0.7) + F("duration_diff")*Value(0.3),
    ).order_by("diff")[:15]

    return queryset


def fund_hedge_position(contract_data, funding_proposal, oracle_message_sequence, position="hedge"):
    response = { "success": False, "fundingTransactionHash": "", "error": "" }

    data = {
        "contractAddress": contract_data["address"],
        "outpointTransactionHash": funding_proposal["txHash"],
        "outpointIndex": funding_proposal["txIndex"],
        "satoshis": funding_proposal["txValue"],
        "signature": funding_proposal["scriptSig"],
        "publicKey": funding_proposal["publicKey"],
        "takerSide": position,
        "dependencyTransactions": funding_proposal["inputTxHashes"],
        "oracleMessageSequence": oracle_message_sequence,
    }
    try:
        resp = requests.post(
            urljoin(app_settings.ANYHEDGE_LP_BASE_URL, "/api/v1/fundContract"),
            data = json.dumps(data),
            headers = {'Content-type': 'application/json', 'Accept': 'text/plain'},
        )
        response_data = resp.json()
        if resp.ok:
            response["success"] = True
            response["fundingTransactionHash"] = response_data["fundingTransactionHash"]
            return response
        else:
            LOGGER.error(f"FUND CONTRACT ERROR: {resp.content}")
            response["success"] = False
            if isinstance(response_data, list) and len(response_data):
                response["error"] = response_data[0]
            elif "errors" in response_data:
                errors = response_data["errors"]
                response["errors"] = errors
                if isinstance(errors, list) and len(errors):
                    response["error"] = errors[0]

            if not response.get("error"):
                response["error"] = response_data
            return response

    except ConnectionError as exception:
        LOGGER.exception(exception)
        response["success"] = False
        response["error"] = "Connection error"
        return response
    except json.JSONDecodeError as exception:
        LOGGER.exception(exception)
        response["success"] = False
        response["error"] = "Encountered error in funding contract"
        return response


def resolve_liquidity_fee(hedge_pos_obj, hard_update=False):
    """
    Populates values for models.HedgePositionMetadata of a models.HedgePosition obj. Also does a funding transaction validation update, if data is available

    Parameters
    ------------
        hedge_position_obj: models.HedgePosition
        hard_update: bool
            If set to true, will update all metadata values even if resolves to "None"
    """
    bchd = get_bchd_instance()
    if not hedge_pos_obj.funding_tx_hash:
        return

    # funding tx data
    tx_data = bchd.get_transaction(hedge_pos_obj.funding_tx_hash, parse_slp=False)
    total_input =  sum([inp["value"] for inp in tx_data["inputs"]])
    total_output =  sum([out["value"] for out in tx_data["outputs"]])
    funding_satoshis = None
    funding_output = None
    for output in tx_data["outputs"]:
        if hedge_pos_obj.address == output["address"]:
            funding_satoshis = output["value"]
            funding_output = output["index"]

    # not really necessary functionality
    # validate contract funding_tx_hash since the data is already available anyway
    if funding_output is not None and funding_satoshis is not None:
        defaults={
            "funding_output": funding_output,
            "funding_satoshis": funding_satoshis,
            "validated": True,
        }

        HedgePositionFunding.objects.update_or_create(
            hedge_position=hedge_pos_obj,
            tx_hash=hedge_pos_obj.funding_tx_hash,
            defaults=defaults
        )
        hedge_pos_obj.funding_tx_hash_validated = True
        hedge_pos_obj.save()

    hedge_sats = hedge_pos_obj.satoshis
    long_sats = hedge_pos_obj.long_input_sats
    total_payout_sats = hedge_sats + long_sats
    network_fee = total_input - total_output
    if funding_satoshis is not None:
        network_fee += funding_satoshis - total_payout_sats

    position_taker = None
    if hedge_pos_obj.hedge_wallet_hash and not hedge_pos_obj.long_wallet_hash:
        position_taker = "hedge"
    elif not hedge_pos_obj.hedge_wallet_hash and hedge_pos_obj.long_wallet_hash:
        position_taker = "long"

    hedge_funding_sats = None
    long_funding_sats = None
    if len(tx_data["inputs"]) == 2:
        # guessing which of 2 inputs is from the hedge/long
        input_0_val = tx_data["inputs"][0]["value"]
        input_1_val = tx_data["inputs"][1]["value"]
        hedge_diff = abs(input_0_val-hedge_sats)
        long_diff = abs(input_0_val-long_sats)
        if long_diff > hedge_diff:
            hedge_funding_sats = input_0_val
            long_funding_sats = input_1_val
        else:
            hedge_funding_sats = input_1_val
            long_funding_sats = input_0_val

    maker_sats, taker_input_sats = None, None
    if position_taker == "hedge":
        maker_sats, taker_input_sats = long_sats, hedge_funding_sats
    elif position_taker == "long":
        maker_sats, taker_input_sats = hedge_sats, long_funding_sats

    liquidity_fee = taker_input_sats - total_input + maker_sats

    metadata_values = {
        "position_taker": position_taker,
        "liquidity_fee": liquidity_fee,
        "network_fee": network_fee,
        "total_hedge_funding_sats": hedge_funding_sats,
        "total_long_funding_sats": long_funding_sats,
    }

    existing_metadata_obj = None
    try:
        existing_metadata_obj = hedge_pos_obj.metadata
    except hedge_pos_obj.__class__.metadata.RelatedObjectDoesNotExist:
        pass

    if existing_metadata_obj and not hard_update:
        if existing_metadata_obj.position_taker:
            metadata_values["position_taker"] = existing_metadata_obj.position_taker
        if existing_metadata_obj.liquidity_fee:
            metadata_values["liquidity_fee"] = existing_metadata_obj.liquidity_fee
        if existing_metadata_obj.network_fee:
            metadata_values["network_fee"] = existing_metadata_obj.network_fee
        if existing_metadata_obj.total_hedge_funding_sats:
            metadata_values["total_hedge_funding_sats"] = existing_metadata_obj.total_hedge_funding_sats
        if existing_metadata_obj.total_long_funding_sats:
            metadata_values["total_long_funding_sats"] = existing_metadata_obj.total_long_funding_sats

    metadata_obj, created = HedgePositionMetadata.objects.update_or_create(
        hedge_position=hedge_pos_obj,
        defaults=metadata_values,
    )

    return metadata_obj
