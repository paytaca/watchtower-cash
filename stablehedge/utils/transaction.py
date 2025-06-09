import re
import math
import decimal

from main import models as main_models
from main.tasks import NODE

class InvalidUtxoException(Exception):
    pass

def validate_utxo_keys(data, require_cashtoken=False, require_nft_token=False, require_unlock=False, raise_error=True):
    try:
        if not isinstance(data, dict):
            raise InvalidUtxoException("Invalid utxo data type")

        keys = set(data.keys())

        required_fields = {"txid", "vout", "satoshis"}    
        cashtoken_fields = {"category", "amount"}
        cashtoken_nft_fields = {"capability", "commitment"}

        if require_cashtoken:
            required_fields.update(cashtoken_fields)
            if require_nft_token:
                required_fields.update(cashtoken_nft_fields)

        if require_unlock:
            required_fields.update({ "locking_bytecode", "unlocking_bytecode" })

        missing_required_fields = required_fields - keys
        if missing_required_fields:
            raise InvalidUtxoException(f"Missing required fields: {missing_required_fields}")

        has_cashtoken_fields = keys.intersection(cashtoken_fields)
        missing_cashtoken_fields = cashtoken_fields - keys
        if has_cashtoken_fields and missing_cashtoken_fields:
            raise InvalidUtxoException(f"Missing required cashtoken fields: {missing_cashtoken_fields}")

        has_cashtoken_nft_fields = keys.intersection(cashtoken_nft_fields)
        missing_cashtoken_nft_fields = {*cashtoken_nft_fields, *cashtoken_fields} - keys
        if has_cashtoken_nft_fields and missing_cashtoken_nft_fields:
            raise InvalidUtxoException(f"Missing required cashtoken nft fields: {missing_cashtoken_nft_fields}")
    except InvalidUtxoException as exception:
        if raise_error: raise exception
        return str(exception)
    return True


def validate_utxo_data(data, require_cashtoken=False, require_nft_token=False,require_unlock=False, raise_error=True):
    try:
        valid_keys = validate_utxo_keys(
            data,
            require_cashtoken=require_cashtoken,
            require_nft_token=require_nft_token,
            require_unlock=require_unlock,
            raise_error=raise_error,
        )

        if isinstance(valid_keys, str): return valid_keys

        if not is_hex_string(data["txid"], require_length=64):
            raise InvalidUtxoException("Invalid txid")

        if not numlike(data["vout"], no_decimal=True):
            raise InvalidUtxoException("Invalid vout")

        if not numlike(data["satoshis"], no_decimal=True):
            raise InvalidUtxoException("Invalid satoshis")

        if require_cashtoken:
            if not is_hex_string(data["category"], require_length=64):
                raise InvalidUtxoException("Invalid category")

            if not numlike(data["amount"], no_decimal=True):
                raise InvalidUtxoException("Invalid amount")

        if require_cashtoken and require_nft_token:
            if not is_hex_string(data["commitment"]) or len(data["commitment"]) > 80:
                raise InvalidUtxoException("Invalid commitment")
            if data["capability"] not in ["none", "mutable", "minting"]:
                raise InvalidUtxoException("Invalid capability")
    except InvalidUtxoException as exception:
        if raise_error: raise exception
        else: return str(exception)

    return True

def utxo_data_to_cashscript(data:dict):
    validate_utxo_data(data)
    response = dict(
        txid=data["txid"],
        vout=data["vout"],
        satoshis=str(data["satoshis"]),
    )
    if "category" in data:
        response["token"] = dict(category = data["category"], amount = str(data["amount"]))

        if "commitment" in data:
            response["token"]["nft"] = dict(
                commitment=data["commitment"],
                capability=data["capability"]
            )

    if "locking_bytecode" in data and "unlocking_bytecode" in data:
        response["lockingBytecode"] = data["locking_bytecode"]
        response["unlockingBytecode"] = data["unlocking_bytecode"]
    elif "wif" in data:
        response["wif"] = data["wif"]
    
    return response


def numlike(value, no_decimal=False):
    if not isinstance(value, (decimal.Decimal, int, str)):
        return False

    if isinstance(value, str) and not re.match("^\d+(\.\d+)?$", value):
        return False

    if no_decimal and value % 1 != 0:
        return False

    return True


def is_hex_string(value, require_length=None):
    valid_hex = re.match("[0-9a-fA-F]*", value)
    if not valid_hex: return False
    if require_length is not None and len(value) != require_length:
        return False
    return True


def tx_model_to_cashscript(obj:main_models.Transaction):
    response = dict(
        txid= obj.txid,
        vout= obj.index,
        satoshis=str(obj.value),
    )
    if obj.cashtoken_ft_id:
        response["token"] = dict(category=obj.cashtoken_ft.category, amount=str(obj.amount))
    if obj.cashtoken_nft:
        response["token"] = dict(
            category=obj.cashtoken_nft.category,
            amount=str(obj.amount),
            nft=dict(
                capability=obj.cashtoken_nft.capability,
                commitment=obj.cashtoken_nft.commitment,
            )
        )

    return response


def get_tx_input_hashes(txid:str):
    txn = NODE.BCH._get_raw_transaction(txid)
    txids = []
    for tx_input in txn['vin']:
        txids.append(tx_input['txid'])
    return txids


def satoshis_to_token(satoshis, price_value):
    satoshis = decimal.Decimal(satoshis)
    token_units_per_bch = decimal.Decimal(price_value)
    token_unit_sats_per_bch = satoshis * token_units_per_bch # <sats(units per bch)> == <units(sats per bch)>

    token_units = math.floor(token_unit_sats_per_bch / 10 ** 8)
    return decimal.Decimal(token_units)

def token_to_satoshis(token_units, price_value):
    token_units = decimal.Decimal(token_units)
    token_units_per_bch = decimal.Decimal(price_value)
    token_unit_sats_per_bch = token_units * 10 ** 8 # <units(sats per bch)> == <sats(units per bch)>
    satoshis = math.floor(token_unit_sats_per_bch / token_units_per_bch)
    return decimal.Decimal(satoshis)

def decode_raw_tx(tx_hex):
    return NODE.BCH._decode_raw_transaction(tx_hex)

def extract_unlocking_script(tx_hex, index=0):
    decoded_tx = NODE.BCH._decode_raw_transaction(tx_hex)
    return decoded_tx["vin"][index]["scriptSig"]["hex"]
