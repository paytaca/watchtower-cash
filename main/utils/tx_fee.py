import re

def is_hex(value):
    return bool(re.match("0x[0-9a-f]*", value, flags=re.IGNORECASE))


def satoshi_to_bch(value):
    return round(value / (10 ** 8), 8)

def get_multisig_input_byte_count(count=0, signers=0, size=0):
    """
        Get byte count of M of N multisig input. Based from bchjs

    Parameters
    -------------------
    count: int
        Number of input of the multisig type
    size: int
        Total number of signatures
    signers: int
        Required number of signatures 

    Returns
    --------------------
    byte count of input
    """
    return (count * 49) + (size * 34) + (signers * 73)


def get_push_data_byte_count(length):
    """
        Getting byte count of the header of OP_RETURN output
    """
    if length < 0x4c:
        # <OP_RETURN><LENGTH:1byte><...>
        return 2
    elif length < 0xff:
        # <OP_RETURN><OP_PUSHDATA1><LENGTH:1byte><...>
        return 3
    elif length < 0xffff:
        # <OP_RETURN><OP_PUSHDATA2><LENGTH:2bytes><...>
        return 4
    else:
        # <OP_RETURN><OP_PUSHDATA3><LENGTH:4bytes><...>
        return 6


def get_hex_byte_count(value):
    if not is_hex(value):
        return None

    length = len(value.replace("0x", ""))/2

    return length + get_push_data_byte_count(length)


def get_utf8_byte_count(value):
    return len(value)


def get_data_byte_count(value):
    if is_hex(value):
        return get_hex_byte_count(value)

    length = get_utf8_byte_count(value)

    return length + get_push_data_byte_count(length)


def get_byte_count(
    p2pkh_input_count=0,
    multisig_inputs=[{'size': 0, 'signers': 0, 'count': 0}],
    p2pkh_output_count=2,
    p2sh_output_count=0,
    push_data=[],
):
    """
        Byte count calculation based from bchjs.
        Options are based from docs

    Returns
    --------------------
    byte count
    """
    BASE_BYTE_COUNT = 10

    total = BASE_BYTE_COUNT
    total += p2pkh_input_count * 148
    for multisig_info in  multisig_inputs:
        total += get_multisig_input_byte_count(**multisig_info)

    total += p2pkh_output_count * 34
    total += p2sh_output_count * 32

    if isinstance(push_data, str):
        total += get
    elif isinstance(push_data, list):
        for push_data_output in push_data:
            total += get_data_byte_count(push_data_output)

    return total


def get_tx_fee_sats(**kwargs):
    """
        Calculate tx fee in satoshi.
        See 'get_byte_count()' for more info
    """
    return get_byte_count(**kwargs) * 1.1


def get_tx_fee_bch(**kwargs):
    """
        Calculate tx fee in bch.
        See 'get_byte_count()' for more info
    """
    return satoshi_to_bch(
        get_tx_fee_sats(**kwargs)
    )
