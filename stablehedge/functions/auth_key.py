from django.conf import settings

from stablehedge.apps import LOGGER
from stablehedge.exceptions import StablehedgeException
from stablehedge.utils.wallet import wif_to_cash_address, subscribe_address
from stablehedge.utils.transaction import tx_model_to_cashscript

from main import models as main_models

def subscribe_auth_key():
    address = get_auth_key_address()
    LOGGER.info(f"Subscribing address holding auth keys: {address}")
    return subscribe_address(address)

def get_auth_key_address():
    wif = settings.STABLEHEDGE["AUTH_KEY_WALLET_WIF"]
    return wif_to_cash_address(wif)

def get_auth_key_utxo(token_category:str):
    address = get_auth_key_address()

    utxo = main_models.Transaction.objects.filter(
        address__address=obj.address,
        cashtoken_nft__category=token_category,
        cashtoken_nft__capability=main_models.CashNonFungibleToken.Capability.NONE,
        spent=False,
    ).first()

    return utxo


def get_signed_auth_key_utxo(token_category:str, locktime:int=0):
    utxo = get_auth_key_utxo(token_category)
    if not utxo:
        raise StablehedgeException(
            f"No auth key utxo found with category: {token_category}",
            code="no-auth-key-utxo",
        )

    ct_utxo = tx_model_to_cashscript(utxo)

    sign_result = ScriptFunctions.signAuthKeyUtxo(dict(locktime=locktime, authKeyUtxo=ct_utxo ))
    if not sign_result["success"]:
        raise StablehedgeException(sign_result.get("error", "Failed to sign auth key utxo"))

    ct_utxo["lockingBytecode"] = sign_result["lockingBytecode"]
    ct_utxo["unlockingBytecode"] = sign_result["unlockingBytecode"]

    return ct_utxo
