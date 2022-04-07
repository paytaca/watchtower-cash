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

def get_byte_count(
    p2pkh_input_count=0,
    multisig_inputs=[{'size': 0, 'signers': 0, 'count': 0}],
    p2pkh_output_count=2,
    p2sh_output_count=0,
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
