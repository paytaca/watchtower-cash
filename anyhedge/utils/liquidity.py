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

def match_hedge_position_to_liquidity_provider(hedge_position_offer_obj, price_oracle_message_sequence:int=None):
    hedge_position_offer_data = {
        "satoshis": hedge_position_offer_obj.satoshis,
        "durationSeconds": hedge_position_offer_obj.duration_seconds,
        "lowLiquidationMultiplier": hedge_position_offer_obj.low_liquidation_multiplier,
        "highLiquidationMultiplier": hedge_position_offer_obj.high_liquidation_multiplier,
        "hedgeAddress": hedge_position_offer_obj.hedge_address,
        "hedgePubkey": hedge_position_offer_obj.hedge_pubkey,
    }

    priceMessageConfig = None
    if hedge_position_offer_obj.oracle_pubkey:
        priceMessageConfig = {
            "oraclePubKey": hedge_position_offer_obj.oracle_pubkey,
        }

    priceMessageRequestParams = None
    if price_oracle_message_sequence:
        priceMessageRequestParams = {
            "minMessageSequence": price_oracle_message_sequence,
            "maxMessageSequence": price_oracle_message_sequence,
        }

    funding_proposal_data = None
    if hedge_position_offer_obj.hedge_funding_proposal:
        funding_proposal_data = {
            "txHash": hedge_position_offer_obj.hedge_funding_proposal.tx_hash,
            "txIndex": hedge_position_offer_obj.hedge_funding_proposal.tx_index,
            "txValue": hedge_position_offer_obj.hedge_funding_proposal.tx_value,
            "scriptSig": hedge_position_offer_obj.hedge_funding_proposal.script_sig,
            "publicKey": hedge_position_offer_obj.hedge_funding_proposal.pubkey,
            "inputTxHashes": hedge_position_offer_obj.hedge_funding_proposal.input_tx_hashes,
        }

    if funding_proposal_data is None:
        return AnyhedgeFunctions.matchHedgePositionOffer(hedge_position_offer_data, priceMessageConfig, priceMessageRequestParams)

    return AnyhedgeFunctions.matchAndFundHedgePositionOffer(hedge_position_offer_data, funding_proposal_data, priceMessageConfig, priceMessageRequestParams)


def fund_hedge_position(contract_data, funding_proposal, oracle_message_sequence):
    return AnyhedgeFunctions.fundHedgePosition(contract_data, funding_proposal, oracle_message_sequence)
