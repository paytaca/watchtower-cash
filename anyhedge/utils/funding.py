import json
import base64
import requests
from cashaddress import convert
from hashlib import sha256
from constance import config as constance_config
from .api import (
    TransactionMetaAttribute,
    parse_tx_wallet_histories,
)
from .contract import (
    compile_contract_from_hedge_position,
)
from ..js.runner import AnyhedgeFunctions

from main.utils.queries.bchn import BCHN
from main.utils.tx_fee import is_hex
from main.utils.address_scan import get_bch_transactions

bchn = BCHN()

def get_tx_hash(tx_hex):
    tx_hex_bytes = bytes.fromhex(tx_hex)
    hash1 = sha256(tx_hex_bytes).digest()
    hash2 = sha256(hash1).digest()
    d = bytearray(hash2)
    d.reverse()
    return d.hex()

def get_p2p_settlement_service_fee():
    DUST_LIMIT = 546
    address = constance_config.P2P_SETTLEMENT_SERVICE_FEE_ADDRESS
    sats = constance_config.P2P_SETTLEMENT_SERVICE_FEE
    try:
        convert.Address._cash_string(address)
    except convert.InvalidAddress:
        return

    if sats < DUST_LIMIT:
        return
    return { "satoshis": sats, "address": address }


def get_gp_lp_service_fee():
    DUST_LIMIT = 546
    address = constance_config.GP_LP_SERVICE_FEE_ADDRESS
    sats = constance_config.GP_LP_SERVICE_FEE
    try:
        convert.Address._cash_string(address)
    except convert.InvalidAddress:
        return

    if sats < DUST_LIMIT:
        return

    return {
        "name": constance_config.GP_LP_SERVICE_FEE_NAME or "Paytaca fee",
        "description": constance_config.GP_LP_SERVICE_FEE_DESCRIPTION or "",
        "satoshis": sats,
        "address": address
    }


def calculate_funding_amounts(contract_data, position="short", premium=0):
    return AnyhedgeFunctions.calculateFundingAmounts(contract_data, position, premium)


def complete_funding_proposal(hedge_position_obj):
    contract_data = compile_contract_from_hedge_position(hedge_position_obj)
    short_funding_proposal = hedge_position_obj.short_funding_proposal
    long_funding_proposal = hedge_position_obj.long_funding_proposal

    if contract_data["address"] != hedge_position_obj.address:
        raise Exception(f"Contract data compilation mismatch, got '{contract_data['address']}' instead of '{hedge_position_obj.address}'")
    
    if short_funding_proposal is None:
        raise Exception(f"{hedge_position_obj} requires hedge funding proposal")
    
    if long_funding_proposal is None:
        raise Exception(f"{hedge_position_obj} requires long funding proposal")

    short_funding_proposal_data = {
        "txHash": short_funding_proposal.tx_hash,
        "txIndex": short_funding_proposal.tx_index,
        "txValue": short_funding_proposal.tx_value,
        "scriptSig": short_funding_proposal.script_sig,
        "publicKey": short_funding_proposal.pubkey,
        "inputTxHashes": short_funding_proposal.input_tx_hashes,
    }

    long_funding_proposal_data = {
        "txHash": long_funding_proposal.tx_hash,
        "txIndex": long_funding_proposal.tx_index,
        "txValue": long_funding_proposal.tx_value,
        "scriptSig": long_funding_proposal.script_sig,
        "publicKey": long_funding_proposal.pubkey,
        "inputTxHashes": long_funding_proposal.input_tx_hashes,
    }

    return AnyhedgeFunctions.completeFundingProposal(
        contract_data, short_funding_proposal_data, long_funding_proposal_data)


def search_funding_tx(contract_address, sats:int=None):
    cash_address = convert.to_cash_address(contract_address)

    history = get_bch_transactions(cash_address)
    txids = [tx["tx_hash"] for tx in history]

    for txid in txids:
        tx_data = bchn._get_raw_transaction(txid)
        for tx_output in tx_data["vout"]:
            if 'value' not in tx_output.keys() or 'addresses' not in tx_output['scriptPubKey'].keys():
                continue

            sats_value = round(tx_output['value'] * (10 ** 8))
            address = tx_output['scriptPubKey']['addresses'][0]

            if address != cash_address:
                continue

            if sats is not None and sats == sats_value:
                return txid
            else:
                return txid

    return ""


def validate_funding_transaction(tx_hash, contract_address):
    response = {
        "valid": False,
        "funding_output": -1,
        "funding_satoshis": 0,
    }
    cash_address = convert.to_cash_address(contract_address)

    if not is_hex(tx_hash, with_prefix=False) or not len(tx_hash) == 64:
        return response

    tx_data = bchn.get_transaction(tx_hash)
    if not tx_data: return response

    for output in tx_data["outputs"]:
        if output["address"] == cash_address:
            response["funding_satoshis"] = output["value"]
            response["funding_output"] = output["index"]
            response["valid"] = True
            break

    return response


def attach_funding_tx_to_wallet_history_meta(hedge_position_obj, force=False):
    if not hedge_position_obj.funding_tx_hash:
        return
    if not hedge_position_obj.funding_tx_hash_validated and not force:
        return

    filter_kwargs = dict(
        txid=hedge_position_obj.funding_tx_hash,
        wallet_hash="",
        system_generated=True,
        key="anyhedge_funding_tx",
    )
    defaults = dict(value=hedge_position_obj.address)

    funding_tx_attr_obj, _ = TransactionMetaAttribute.objects.update_or_create(defaults=defaults, **filter_kwargs)

    hedge_meta, long_meta = None, None
    if hedge_position_obj.short_wallet_hash and hedge_position_obj.short_funding_proposal:
        parse_tx_wallet_histories(
            hedge_position_obj.short_funding_proposal.tx_hash,
            proceed_with_zero_amount=True,
            immediate=True
        )
        filter_kwargs["txid"] = hedge_position_obj.short_funding_proposal.tx_hash
        filter_kwargs["wallet_hash"] = hedge_position_obj.short_wallet_hash
        filter_kwargs["key"] = "anyhedge_hedge_funding_utxo"
        hedge_meta, _ = TransactionMetaAttribute.objects.update_or_create(defaults=defaults, **filter_kwargs)

    if hedge_position_obj.long_wallet_hash and hedge_position_obj.long_funding_proposal:
        parse_tx_wallet_histories(
            hedge_position_obj.long_funding_proposal.tx_hash,
            proceed_with_zero_amount=True,
            immediate=True
        )
        filter_kwargs["txid"] = hedge_position_obj.long_funding_proposal.tx_hash
        filter_kwargs["key"] = "anyhedge_long_funding_utxo"
        filter_kwargs["wallet_hash"] = hedge_position_obj.long_wallet_hash
        long_meta, _ = TransactionMetaAttribute.objects.update_or_create(defaults=defaults, **filter_kwargs)

    return (funding_tx_attr_obj, hedge_meta, long_meta)
