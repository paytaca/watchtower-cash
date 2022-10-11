import json
import requests
from django.db.models import OuterRef, Subquery, Sum, F, Value
from django.db.models.functions import Coalesce, Greatest
from ..js.runner import AnyhedgeFunctions
from ..models import (
    LongAccount,
)
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
