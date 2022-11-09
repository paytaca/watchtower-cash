import json
import requests
from django.db.models import OuterRef, Subquery, Sum, F, Value
from django.db.models.functions import Coalesce, Greatest
from ..js.runner import AnyhedgeFunctions
from ..models import (
    LongAccount,
    HedgePositionFunding,
    HedgePositionMetadata,
)
from .api import get_bchd_instance
from .websocket import send_long_account_update


def get_position_offer_suggestions(amount=0, duration_seconds=0, low_liquidation_multiplier=0.9, high_liquidation_multiplier=10, exclude_wallet_hash=""):
    # NOTE: long_amount_needed is an estimate and may be off by a bit from the actual amount needed, this is due to;
    # missing oracle price
    long_amount_needed = (amount / low_liquidation_multiplier) - amount

    return LongAccount.objects.filter(
        auto_accept_allowance__gte=long_amount_needed,
        min_auto_accept_duration__lte=duration_seconds,
        max_auto_accept_duration__gte=duration_seconds,
    ).exclude(
        wallet_hash=exclude_wallet_hash,
    ).order_by('auto_accept_allowance')


def consume_long_account_allowance(long_address, long_input_sats):
    querylist = LongAccount.objects.filter(address=long_address)
    resp = querylist.update(auto_accept_allowance= Greatest(F("auto_accept_allowance") - long_input_sats, Value(0)))

    wallet_hashes =  querylist.values_list('wallet_hash', flat=True).distinct()
    for wallet_hash in wallet_hashes:
        send_long_account_update(wallet_hash, action="consume_allowance")
    return resp

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
            "https://staging-liquidity.anyhedge.com/api/v1/fundContract",
            data = json.dumps(data),
            headers = {'Content-type': 'application/json', 'Accept': 'text/plain'},
        )
        response_data = resp.json()
        if resp.ok:
            response["success"] = True
            response["fundingTransactionHash"] = response_data["fundingTransactionHash"]
            return response
        else:
            if isinstance(response_data, list) and len(response_data):
                response["success"] = False
                response["error"] = response_data[0]
                return response
            else:
                response["success"] = False
                response["error"] = "Encountered error in funding contract"
                return response

    except ConnectionError:
        response["success"] = False
        response["error"] = "Connection error"
        return response
    except json.JSONDecodeError:
        response["success"] = False
        response["error"] = "Encountered error in funding contract"
        return response
    # return AnyhedgeFunctions.fundHedgePosition(contract_data, funding_proposal, oracle_message_sequence, position)


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
    fee_satoshis = None
    fee_output = None
    for output in tx_data["outputs"]:
        if hedge_pos_obj.address == output["address"]:
            funding_satoshis = output["value"]
            funding_output = output["index"]
        elif hedge_pos_obj.fee and hedge_pos_obj.fee.address == output["address"]:
            fee_satoshis = output["value"]
            fee_output = output["index"]

    # not really necessary functionality
    # validate contract funding_tx_hash since the data is already available anyway
    if funding_output is not None and funding_satoshis is not None:
        defaults={
            "funding_output": funding_output,
            "funding_satoshis": funding_satoshis,
        }
        if fee_output is not None and fee_satoshis is not None:
            defaults["fee_output"] = fee_output
            defaults["fee_satoshis"] = fee_satoshis

        HedgePositionFunding.objects.update_or_create(tx_hash=hedge_pos_obj.funding_tx_hash, defaults=defaults)
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

    liqiudidty_fee = taker_input_sats - total_input + maker_sats

    metadata_values = {
        "position_taker": position_taker,
        "liqiudidty_fee": liqiudidty_fee,
        "network_fee": network_fee,
        "total_hedge_funding_sats": hedge_funding_sats,
        "total_long_funding_sats": long_funding_sats,
    }

    if hedge_position_obj.metadata and not hard_update:
        existing_metadata_obj = hedge_position_obj.metadata
        if existing_metadata_obj.position_taker:
            metadata_values["position_taker"] = existing_metadata_obj.position_taker
        if existing_metadata_obj.liqiudidty_fee:
            metadata_values["liqiudidty_fee"] = existing_metadata_obj.liqiudidty_fee
        if existing_metadata_obj.network_fee:
            metadata_values["network_fee"] = existing_metadata_obj.network_fee
        if existing_metadata_obj.total_hedge_funding_sats:
            metadata_values["total_hedge_funding_sats"] = existing_metadata_obj.total_hedge_funding_sats
        if existing_metadata_obj.total_long_funding_sats:
            metadata_values["total_long_funding_sats"] = existing_metadata_obj.total_long_funding_sats

    metadata_obj, created = HedgePositionMetadata.objects.update_or_create(
        hedge_position=hedge_pos_obj,
        defaults=default,
    )

    return metadata_obj
