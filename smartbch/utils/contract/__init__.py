import json
import requests
import functools
import web3
from web3 import exceptions
from smartbch.models import TokenContract

from ..web3 import create_web3_client
from .abi import get_token_abi


def fetch_icons_from_marketcap():
    """
        Fetch token icon urls listed in marketcap.cash

    Returns
    --------------------
    address_image_url_map: Map<Address, URL>
        address is in lowercase to prevent mismatch due to case sensitivity
    """
    marketcap_token_list_json_url = "https://raw.githubusercontent.com/MarketCap-Cash/SmartBCH-Token-List/main/tokens.json"
    response = requests.get(marketcap_token_list_json_url)
    if not response.ok:
        return None

    data = {}
    try:
        data = response.json()
    except json.decoder.JSONDecodeError:
        pass

    address_image_map = {}
    for _, token_info in data.items():
        if "address" not in token_info or "image" not in token_info:
            continue

        if not token_info["address"] or not token_info["image"]:
            continue
    
        address_image_map[f"{token_info['address']}".lower()] = token_info["image"]

    return address_image_map


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

def _truncate_text(name, length):
    if isinstance(name, str):
        return name[0:length]
    else:
        return ''

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
        address=address,
        defaults={
            "name": _truncate_text(name, 100),
            "symbol": _truncate_text(symbol, 50),
        }
    )

    return instance, updated

def get_token_decimals(address):
    """
        Get decimal count of SEP-20 token

    Return
    ------------------
        int,None
    """
    if not web3.Web3.isAddress(address):
        return None, None

    w3 = create_web3_client()
    contract = w3.eth.contract(address, abi=get_token_abi(20))
    try:
        return contract.functions.decimals().call()
    except exceptions.ContractLogicError:
        return None
