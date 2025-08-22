# from subprocess import Popen, PIPE
from django.conf import settings
from cashaddress import convert
import requests
import json


SLP_MAIN_ADDR_LEN = 55
SLP_TEST_ADDR_LEN = 50


def is_slp_address(addr, check_len=True):
    prefix_check = addr.startswith('slptest:')
    basis_len = SLP_TEST_ADDR_LEN

    if settings.BCH_NETWORK == 'mainnet':
        prefix_check = addr.startswith('simpleledger:')
        basis_len = SLP_MAIN_ADDR_LEN

    if check_len:
        return prefix_check and len(addr) == basis_len
    return prefix_check


def is_bch_address(addr, to_token_addr=False):

    if addr:
        if is_slp_address(addr):
            return False

        result = { 'valid': False }
        url = f'http://localhost:3000/validate-address/{addr}?token={to_token_addr}'
        resp = requests.get(url)
        result = resp.json()
        return result['valid']
    
    return False


def is_token_address(addr):
    return is_bch_address(addr, to_token_addr=True)


def is_p2sh_address(addr):
    try:
        decoded = convert.Address.from_string(addr)
        return decoded.version == 'P2SH32'
    except Exception:
        return False
