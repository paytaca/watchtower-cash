import json
import base64
import requests
from cashaddress import convert
from hashlib import sha256
from .contract import compile_contract_from_hedge_position
from ..js.runner import AnyhedgeFunctions


def get_tx_hash(tx_hex):
    tx_hex_bytes = bytes.fromhex(tx_hex)
    hash1 = sha256(tx_hex_bytes).digest()
    hash2 = sha256(hash1).digest()
    d = bytearray(hash2)
    d.reverse()
    return d.hex()


def calculate_funding_amounts(hedge_position_obj):
    contract_data = compile_contract_from_hedge_position(hedge_position_obj)

    if contract_data["address"] != hedge_position_obj.address:
        raise Exception(f"Contract data compilation mismatch, got '{contract_data['address']}' instead of '{hedge_position_obj.address}'")
    
    return AnyhedgeFunctions.calculateFundingAmounts(contract_data, "hedge")


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

# form a task for doing the full funding processs
# add function for searching funding tx hash of contract from blockchain
# utxo validation function