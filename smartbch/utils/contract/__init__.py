import functools
import web3
from smartbch.models import TokenContract

from ..web3 import create_web3_client
from .abi import get_token_abi


def is_contract(address):
    w3 = create_web3_client()
    return len(w3.eth.get_code(address)) > 5


def save_if_contract(address):
    instance = TokenContract.objects.filter(address=address).first()
    exists = instance is not None

    if not exists:
        if is_contract(address):
            instance, created = TokenContract.objects.get_or_create(address=address)
            exists = True

    return instance


@functools.lru_cache(maxsize=None)
def get_token_contract_metadata(address):
    """
    Return
    -----------
    (name, symbol): tuple
        name: string or None
        symbol string or None
    """
    if not web3.Web3.isAddress(address):
        return None, None

    w3 = create_web3_client()
    contract = w3.eth.contract(address, abi=get_token_abi(20))

    name = None
    symbol = None

    try:
        name = contract.functions.name().call()
    except (web3.exceptions.BadFunctionCallOutput, web3.exceptions.ABIFunctionNotFound):
        pass

    try:
        symbol = contract.functions.symbol().call()
    except (web3.exceptions.BadFunctionCallOutput, web3.exceptions.ABIFunctionNotFound):
        pass

    return name, symbol


def get_or_save_token_contract_metadata(address, force=False):
    """
    Return
    -----------
        (token_contract, updated):
            token_contract: TokenContract instance or None
            updated: if instance is updated
    """
    if not web3.Web3.isAddress(address):
        return None, None

    token_contract = TokenContract.objects.filter(address=address, name__isnull=False, symbol__isnull=False).first()
    if token_contract and not force:
        return token_contract, False

    name, symbol = get_token_contract_metadata(address)
    instance, updated = TokenContract.objects.update_or_create(
        addresss=address,
        defaults={
            "name": name or "",
            "symbol": symbol or "",
        }
    )

    return instance, updated
