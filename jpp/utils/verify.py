from bitcoinrpc.authproxy import JSONRPCException

from main.utils.address_converter import address_to_locking_bytecode
from main.utils.queries.bchn import BCHN
from main.utils.tx_fee import is_hex

bchn = BCHN()

def __is_txid(txid):
    return is_hex(txid, with_prefix=False) and len(txid) == 64

class VerifyError(Exception):
    pass


def compare_output(tx_output, invoice_output):
    script_pubkey = address_to_locking_bytecode(invoice_output.address)
    if script_pubkey != tx_output["scriptPubKey"]["hex"]:
        return False

    satoshis = round(tx_output.get("value", 0) * 1e8)
    if satoshis != invoice_output.amount:
        return False

    # address & amount would be equal at this point
    # but if there is no tokenData it would only be equal if invoice_output has no category also
    if "tokenData" not in tx_output:
        return not bool(invoice_output.category)

    token_data = tx_output["tokenData"]
    if token_data["category"] != invoice_output.category:
        return False

    if int(token_data["amount"]) != invoice_output.token_amount or 0:
        return False
    
    if "nft" not in token_data:
        return not bool(invoice_output.capability)
    
    nft_data = token_data["nft"]
    if nft_data["capability"] != invoice_output.capability:
        return False

    if nft_data["commitment"] != invoice_output.commitment or "":
        return False

    return True


def verify_tx_hex(invoice_obj, tx_hex, verify_inputs=True):
    tx = bchn.build_tx_from_hex(tx_hex)
    invoice_outputs = invoice_obj.outputs.all()

    matched_output_indices = []
    for invoice_output in invoice_outputs:
        found_match = False
        for tx_output in tx["vout"]:
            if tx_output["n"] in matched_output_indices:
                continue

            if compare_output(tx_output, invoice_output):
                matched_output_indices.append(tx_output["n"])
                found_match = True
                break

        if not found_match:
            raise VerifyError("Missing expected output" + f"{invoice_output}")

    if verify_inputs:
        tx_total_input = int(sum([vin["value"] for vin in tx["vin"]]) * 1e8)
        tx_total_output = int(sum([vout["value"] for vout in tx["vout"]]) * 1e8)

        if tx_total_input < tx_total_output:
            raise VerifyError(f"Total input {tx_total_input} satoshis is less than total output {tx_total_output} satoshis")

        tx_fee = tx_total_input - tx_total_output
        expected_tx_fee = invoice_obj.required_fee_per_byte * tx["size"]
        if tx_fee < expected_tx_fee:
            raise VerifyError(f"Expected tx fee of {expected_tx_fee} satoshis but got {tx_fee} satoshis")

    return True

def tx_exists(txid):
    if not __is_txid(txid): return False
    try:
        transaction = bchn._get_raw_transaction(txid, 0, max_retries=2)
        return bool(transaction)
    except JSONRPCException as exception:
        if exception.code in [-5, -8]: # -5 -> doesnt exist, -8 -> invalid txid format(32byte hex)
            return False
        raise exception
