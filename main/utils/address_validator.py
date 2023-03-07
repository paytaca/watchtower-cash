BCH_MAIN_PREFIX = 'bitcoincash:'
BCH_TEST_PREFIX = 'bchtest:'
BCH_ADDR_LEN = 54
SLP_ADDR_LEN = 55

def is_bch_address(addr, check_len=True):
    prefix_check = (
        addr.startswith(f'{BCH_MAIN_PREFIX}q') or
        addr.startswith(f'{BCH_MAIN_PREFIX}p') or
        addr.startswith(f'{BCH_TEST_PREFIX}q') or
        addr.startswith(f'{BCH_TEST_PREFIX}p')
    )
    if check_len:
        return prefix_check and len(addr) == BCH_ADDR_LEN
    return prefix_check

def is_token_address(addr, check_len=True):
    prefix_check = (
        addr.startswith(f'{BCH_MAIN_PREFIX}z') or
        addr.startswith(f'{BCH_TEST_PREFIX}z')
    )
    if check_len:
        return prefix_check and len(addr) == BCH_ADDR_LEN
    return prefix_check

def is_slp_address(addr, check_len=True):
    prefix_check = (
        addr.startswith('simpleledger:') or
        addr.startswith('slptest:')
    )
    if check_len:
        return prefix_check and len(addr) == SLP_ADDR_LEN
    return prefix_check

