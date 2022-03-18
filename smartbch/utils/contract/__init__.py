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

def save_token_contract_metadata(address, check_address=True):
    w3 = create_web3_client()
    contract = w3.eth.contract(address, abi=get_token_abi(20))

    if check_address and not is_contract(address):
        return

    defaults = {}
    try:
        defaults["name"] = contract.functions.name().call()
    except (web3.exceptions.BadFunctionCallOutput, web3.exceptions.ABIFunctionNotFound):
        defaults["name"] = ""

    try:
        defaults["symbol"] = contract.functions.symbol().call()
    except (web3.exceptions.BadFunctionCallOutput, web3.exceptions.ABIFunctionNotFound):
        defaults["symbol"] = ""

    instance, updated = TokenContract.objects.update_or_create(
        addresss=address,
        defaults=defaults
    )

    return instance
