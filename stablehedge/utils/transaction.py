import re
import decimal

from main import models as main_models

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
            if not is_hex_string(data["commitment"]) or not len(data["commitment"]) < 40:
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
        satoshis=data["satoshis"],
    )
    if "category" in data:
        response["token"] = dict(category = data["category"], amount = data["amount"])

        if "commitment" in data:
            response["token"]["nft"] = dict(
                commitment=data["commitment"],
                capability=data["capability"]
            )

    if "locking_bytecode" in data and "unlocking_bytecode" in data:
        response["lockingBytecode"] = data["locking_bytecode"]
        response["unlockingBytecode"] = data["unlocking_bytecode"]
    
    return response


def numlike(value, no_decimal=False):
    if not isinstance(value, (decimal.Decimal, int)):
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
        satoshis= obj.value,
    )
    if obj.cashtoken_ft_id:
        response["token"] = dict(category=obj.cashtoken_ft.category, amount=obj.amount)
    if obj.cashtoken_nft:
        response["token"] = dict(
            category=obj.cashtoken_nft.category,
            amount=obj.amount,
            nft=dict(
                capability=obj.cashtoken_nft.capability,
                commitment=obj.cashtoken_nft.commitment,
            )
        )

    return response
