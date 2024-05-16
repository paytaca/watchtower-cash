import json
import base64
import requests

import traceback
import bitcoin
from cashaddress import convert
from bitcoinrpc.authproxy import JSONRPCException

from main.utils.queries.bchn import BCHN
from main.utils.tx_fee import is_hex

bchn = BCHN()

def __is_txid(txid):
    return is_hex(txid, with_prefix=False) and len(txid) == 64

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
    txs_data = []
    for txid in txids:
        if not __is_txid(txid): continue

        try:
            txs_data.append(bchn.get_transaction(txid))
        except Exception as exception:
            txs_data.append(exception)

    txs_map = {}
    for tx_data in txs_data:
        if not isinstance(tx_data, dict): continue

        output_map = {}
        for output in tx_data["outputs"]:
            output_map[output["index"]] = output["value"]
        txs_map[tx_data["txid"]] = output_map
    return txs_map


def tx_exists(txid):
    if not __is_txid(txid): return False
    try:
        bchn.rpc_connection.getrawtransaction(txid, 0)
        return True
    except JSONRPCException as exception:
        if exception.code in [-5, -8]: # -5 -> doesnt exist, -8 -> invalid txid format(32byte hex)
            return False
        raise exception

        return False
