from subprocess import Popen, PIPE
from django.conf import settings
import json


SLP_MAIN_ADDR_LEN = 55
BCH_TEST_ADDR_LEN = 50
SLP_TEST_ADDR_LEN = 50


def is_bch_address(addr, to_token_addr=False):
    cmd = f'node main/js/validate-address.js {bch_addr} {to_token_addr}'
    p = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE)
    stdout, stderr = p.communicate()
    result = json.loads(stdout.decode('utf8'))
    return result['valid']


def is_token_address(addr):
    is_bch_address(addr, to_token_addr=True)


def is_slp_address(addr, check_len=True):
    prefix_check = addr.startswith('slptest:')
    basis_len = SLP_TEST_ADDR_LEN

    if settings.BCH_NETWORK == 'mainnet':
        prefix_check = addr.startswith('simpleledger:')
        basis_len = SLP_MAIN_ADDR_LEN

    if check_len:
        return prefix_check and len(addr) == basis_len
    return prefix_check

