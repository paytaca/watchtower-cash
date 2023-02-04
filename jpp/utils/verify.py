import json
import base64
import requests

import traceback
import bitcoin
from cashaddress import convert


class VerifyError(Exception):
    pass


def verify_tx_hex(invoice_obj, tx_hex, verify_inputs=True):
    tx = parse_tx_hex(tx_hex, with_input_values=verify_inputs)

    invoice_output_value_map = {} # Map<address:str, total_value:int>
    for output in invoice_obj.outputs.all():
        if not invoice_output_value_map.get(output.address, None):
            invoice_output_value_map[output.address] = 0
        invoice_output_value_map[output.address] += output.amount

    tx_output_value_map = {} # Map<address:str, total_value:int>
    for output in tx["outs"]:
        if not tx_output_value_map.get(output["address"], None):
                tx_output_value_map[output["address"]] = 0
        tx_output_value_map[output["address"]] += output["value"]

    for address, amount in invoice_output_value_map.items():
        if address not in tx_output_value_map:
            raise VerifyError(f"Expected output for '{address}'")

        if amount != tx_output_value_map[address]:
            raise VerifyError(f"Expected {amount} satoshis for '{address}', got {tx_output_value_map[address]}")

    if verify_inputs:
        tx_total_input = tx["total_input"]
        tx_total_output = tx["total_output"]
        if tx_total_input < tx_total_output:
            raise VerifyError(f"Total input {tx_total_input} satoshis is less than total output {tx_total_output} satoshis")

        tx_fee = tx["tx_fee"]
        expected_tx_fee = invoice_obj.required_fee_per_byte * tx["byte_count"]
        if tx_fee < expected_tx_fee:
            raise VerifyError(f"Expected tx fee of {expected_tx_fee} satoshis but got {tx_fee} satoshis")

    return True


def parse_tx_hex(tx_hex, with_input_values=True):
    tx = bitcoin.deserialize(tx_hex)
    byte_count = len(tx_hex) / 2 # 1 byte (8bits) is 2 hex(4bits)
    tx["byte_count"] = byte_count
    tx["hash"] = bitcoin.txhash(tx_hex)

    for output in tx["outs"]:
        try:
            output["address"] = convert.to_cash_address(
                bitcoin.script_to_address(output["script"])
            )
        except Exception:
            traceback.print_exc()

    if with_input_values:
        txids = [inp["outpoint"]["hash"] for inp in tx["ins"]]
        tx_inp_value_map = get_tx_output_values(txids)
        for inp in tx["ins"]:
            outpoint_txid = inp["outpoint"]["hash"]
            outpoint_index = inp["outpoint"]["index"]
            value_map = tx_inp_value_map.get(outpoint_txid)
            if not value_map:
                continue

            if outpoint_index in value_map:
                inp["value"] = value_map[outpoint_index]
    
        tx_total_output = 0
        for output in tx["outs"]:
            tx_total_output += output["value"]

        tx_total_input = 0
        for inp in tx["ins"]:
            tx_total_input += inp["value"]

        tx["total_output"] = tx_total_output
        tx["total_input"] = tx_total_input
        tx["tx_fee"] = tx_total_input - tx_total_output

    return tx


def get_tx_output_values(txids):
    """
    Parameters:
        txids:str[] - array of txids
            example: [ 'e4ae...0f3cd', '80b7...9c496' ]
    Returns:
        tx_output_map: Map<txid:str, Map<output_index:int, value:int>>
    """

    txids = list(set(txids))
    query = {
        "v": 3,
        "q": {
            "find": { "tx.h": { "$in": txids } },
            "project": { "tx.h": 1, "out.e.i": 1, "out.e.v": 1 },
        }
    }
    query_string = json.dumps(query)
    query_bytes = query_string.encode('ascii')
    query_b64 = base64.b64encode(query_bytes)

    url = f"https://bitdb.bch.sx/q/{query_b64.decode()}"
    data = requests.get(url).json()
    txs = [*data["c"], *data["u"]]
    tx_output_map = {} # Map(txid, Map(output_index, value) )
    for tx in txs:
        txid = tx["tx"]["h"]
        output_map = {} # output_index => value
        for output in tx["out"]:
            index = output["e"]["i"]
            value = output["e"]["v"]
            output_map[index] = value

        tx_output_map[txid] = output_map

    return tx_output_map

def tx_exists(txid):
    query = {
        "v": 3,
        "q": {
            "find": { "tx.h": txid },
            "project": { "tx.h": 1 },
        }
    }
    query_string = json.dumps(query)
    query_bytes = query_string.encode('ascii')
    query_b64 = base64.b64encode(query_bytes)

    url = f"https://bitdb.bch.sx/q/{query_b64.decode()}"
    data = requests.get(url).json()
    txs = [*data["c"], *data["u"]]

    return len(txs) > 0
