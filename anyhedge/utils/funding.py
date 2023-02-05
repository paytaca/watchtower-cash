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
    calculate_hedge_sats,
)
from ..js.runner import AnyhedgeFunctions


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


def calculate_funding_amounts(contract_data, position="hedge", premium=0):
    return AnyhedgeFunctions.calculateFundingAmounts(contract_data, position, premium)


def complete_funding_proposal(hedge_position_obj):
    contract_data = compile_contract_from_hedge_position(hedge_position_obj)
    hedge_funding_proposal = hedge_position_obj.hedge_funding_proposal
    long_funding_proposal = hedge_position_obj.long_funding_proposal

    if contract_data["address"] != hedge_position_obj.address:
        raise Exception(f"Contract data compilation mismatch, got '{contract_data['address']}' instead of '{hedge_position_obj.address}'")
    
    if hedge_funding_proposal is None:
        raise Exception(f"{hedge_position_obj} requires hedge funding proposal")
    
    if long_funding_proposal is None:
        raise Exception(f"{hedge_position_obj} requires long funding proposal")

    hedge_funding_proposal_data = {
        "txHash": hedge_funding_proposal.tx_hash,
        "txIndex": hedge_funding_proposal.tx_index,
        "txValue": hedge_funding_proposal.tx_value,
        "scriptSig": hedge_funding_proposal.script_sig,
        "publicKey": hedge_funding_proposal.pubkey,
        "inputTxHashes": hedge_funding_proposal.input_tx_hashes,
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
        contract_data, hedge_funding_proposal_data, long_funding_proposal_data)


def search_funding_tx(contract_address, sats:int=None):
    cash_address = convert.to_cash_address(contract_address)
    address = cash_address.replace("bitcoincash:", "")
    query = {
        "v": 3,
        "q": {
            "find": {
            "out.e.a": address
            },
            "limit": 10,
            "project": { "tx.h": 1, "out.e": 1 },
        },
        # "r": {
        #     "f": "[.[] | { hash: .tx.h?, out: .out[].e? }  ]"
        # }
    }
    query_string = json.dumps(query)
    query_bytes = query_string.encode('ascii')
    query_b64 = base64.b64encode(query_bytes)
    url = f"https://bitdb.bch.sx/q/{query_b64.decode()}"
    
    data = requests.get(url).json()
    # example data structure:
    # {
    #     "u": [],
    #     "c": [
    #         {
    #             "_id": "63241ec4b8ba1c709088ada9",
    #             "tx": { "h": "1499ac29cf09f6752cdc54b4df8ffa9dbb8f7393b99e8380b2d6ce9363341ef4" },
    #             "out": [
    #                 {
    #                     "e": { "v": 1251123, "i": 0, "a": "pzjjvtqc686qr75ghnlaqs2y9dsdalqczcwshgpaaj" }
    #                 },
    #                 {
    #                     "e": { "v": 546, "i": 1, "a": "qp03erh5c9nmk0s830vpn39faxw3fq0vxsp870x46u" }
    #                 }
    #             ]
    #         }
    #     ]
    # }

    txs = [*data["c"], *data["u"]]
    for tx in txs:
        tx_hash = tx["tx"]["h"]
        if sats is not None:
            for output in tx["out"]:
                if output["e"]["v"] == sats:
                    return tx_hash
        else:
            return tx_hash

    return ""


def validate_funding_transaction(tx_hash, contract_address):
    response = {
        "valid": False,
        "funding_output": -1,
        "funding_satoshis": 0,
    }
    cash_address = convert.to_cash_address(contract_address)
    address = cash_address.replace("bitcoincash:", "")

    query = {
        "v": 3,
        "q": {
            "find": {
                "tx.h": tx_hash,
                "out.e.a": address,
            },
            "limit": 10,
            "project": { "tx.h": 1, "out.e": 1 },
        },
        # "r": {
        #     "f": "[.[] | { hash: .tx.h?, out: .out[].e? }  ]"
        # }
    }
    query_string = json.dumps(query)
    query_bytes = query_string.encode('ascii')
    query_b64 = base64.b64encode(query_bytes)
    url = f"https://bitdb.bch.sx/q/{query_b64.decode()}"
    data = requests.get(url).json()

    txs = [*data["c"], *data["u"]]
    for tx in txs:
        if tx["tx"]["h"] != tx_hash:
            continue

        for output in tx["out"]:
            if output["e"]["a"] == address:
                response["funding_satoshis"] = output["e"]["v"]
                response["funding_output"] = output["e"]["i"]
                response["valid"] = True

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
    if hedge_position_obj.hedge_wallet_hash and hedge_position_obj.hedge_funding_proposal:
        parse_tx_wallet_histories(
            hedge_position_obj.hedge_funding_proposal.tx_hash,
            proceed_with_zero_amount=True,
        )
        filter_kwargs["txid"] = hedge_position_obj.hedge_funding_proposal.tx_hash
        filter_kwargs["wallet_hash"] = hedge_position_obj.hedge_wallet_hash
        filter_kwargs["key"] = "anyhedge_hedge_funding_utxo"
        hedge_meta, _ = TransactionMetaAttribute.objects.update_or_create(defaults=defaults, **filter_kwargs)

    if hedge_position_obj.long_wallet_hash and hedge_position_obj.long_funding_proposal:
        parse_tx_wallet_histories(
            hedge_position_obj.long_funding_proposal.tx_hash,
            proceed_with_zero_amount=True,
        )
        filter_kwargs["txid"] = hedge_position_obj.long_funding_proposal.tx_hash
        filter_kwargs["key"] = "anyhedge_long_funding_utxo"
        filter_kwargs["wallet_hash"] = hedge_position_obj.long_wallet_hash
        long_meta, _ = TransactionMetaAttribute.objects.update_or_create(defaults=defaults, **filter_kwargs)

    return (funding_tx_attr_obj, hedge_meta, long_meta)
