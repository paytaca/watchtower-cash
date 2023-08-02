from subprocess import Popen, PIPE
from django.conf import settings
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
    if is_slp_address(addr):
        return False

    cmd = f'node main/js/validate-address.js {addr} {to_token_addr}'
    p = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE)
    stdout, _ = p.communicate()
    result = json.loads(stdout.decode('utf8'))
    return result['valid']


def is_token_address(addr):
    is_bch_address(addr, to_token_addr=True)
