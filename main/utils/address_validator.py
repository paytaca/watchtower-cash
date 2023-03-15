from django.conf import settings

BCH_MAIN_PREFIX = 'bitcoincash:'
BCH_TEST_PREFIX = 'bchtest:'
BCH_MAIN_ADDR_LEN = 54
SLP_MAIN_ADDR_LEN = 55
BCH_TEST_ADDR_LEN = 50
SLP_TEST_ADDR_LEN = 50

IS_MAINNET = settings.BCH_NETWORK == 'mainnet'


def is_bch_address(addr, check_len=True):
    prefix_check = (
        addr.startswith(f'{BCH_TEST_PREFIX}q') or
        addr.startswith(f'{BCH_TEST_PREFIX}p')
    )
    basis_len = BCH_TEST_ADDR_LEN

    if IS_MAINNET:
        prefix_check = (
            addr.startswith(f'{BCH_MAIN_PREFIX}q') or
            addr.startswith(f'{BCH_MAIN_PREFIX}p')
        )
        basis_len = BCH_MAIN_ADDR_LEN

    if check_len:
        return prefix_check and len(addr) == basis_len
    return prefix_check


def is_token_address(addr, check_len=True):
    prefix_check = addr.startswith(f'{BCH_TEST_PREFIX}z')
    basis_len = BCH_TEST_ADDR_LEN

    if IS_MAINNET:
        prefix_check = addr.startswith(f'{BCH_MAIN_PREFIX}z')
        basis_len = BCH_MAIN_ADDR_LEN

    if check_len:
        return prefix_check and len(addr) == basis_len
    return prefix_check


def is_slp_address(addr, check_len=True):
    prefix_check = addr.startswith('slptest:')
    basis_len = SLP_TEST_ADDR_LEN

    if IS_MAINNET:
        prefix_check = addr.startswith('simpleledger:')
        basis_len = SLP_MAIN_ADDR_LEN

    if check_len:
        return prefix_check and len(addr) == basis_len
    return prefix_check

