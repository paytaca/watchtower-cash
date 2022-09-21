import json
import base64
import requests
from cashaddress import convert
from .contract import compile_contract_from_hedge_position
from ..js.runner import AnyhedgeFunctions

def search_settlement_tx(contract_address):
    cash_address = convert.to_cash_address(contract_address)
    address = cash_address.replace("bitcoincash:", "")
    query = {
        "v": 3,
        "q": {
            "find": { "in.e.a": address },
            "limit": 10,
            "project": { "tx.h": 1 },
        }
    }

    # get used utxos of contract address
    query_string = json.dumps(query)
    query_bytes = query_string.encode('ascii')
    query_b64 = base64.b64encode(query_bytes)
    url = f"https://bitdb.bch.sx/q/{query_b64.decode()}"

    data = requests.get(url).json()
    tx_hashes = []

    txs = [*data["c"], *data["u"]]
    for tx in txs:
        tx_hashes.append(tx["tx"]["h"])

    if len(tx_hashes) == 0:
        return []

    # get raw transactions of used utxos
    response = requests.post(
        "https://rest1.biggestfan.net/v2/rawtransactions/getRawTransaction",
        data = json.dumps({ "txids": tx_hashes, "verbose": False }),
        headers = {'Content-type': 'application/json', 'Accept': 'text/plain'},
    )
    raw_transactions = response.json()
    if not isinstance(raw_transactions, list):
        return []

    # parse raw transactions to settlements
    parse_settlement_txs_response = AnyhedgeFunctions.parseSettlementTransactions(raw_transactions)

    settlements = []
    if not parse_settlement_txs_response["success"]:
        return settlements

    for settlement in parse_settlement_txs_response["settlements"]:
        if not settlement:
            continue
        
        if settlement["address"] == contract_address:
            settlements.append(settlement)

    return settlements


def settle_hedge_position_maturity(hedge_position_obj):
    contract_data = compile_contract_from_hedge_position(hedge_position_obj)

    oracle = Oracle.objects.filter(pubkey=hedge_position_obj.oracle_pubkey).first()
    oracle_info = None
    if oracle and oracle.relay and oracle.port:
        oracle_info = {
            "oracleRelay": oracle.relay,
            "oracleRelayPort": oracle.port,
        }

    return AnyhedgeFunctions.settleContractMaturity(contract_data, oracle_info)
