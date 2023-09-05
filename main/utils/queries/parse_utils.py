def extract_tx_utxos(bch_tx:dict):
    inputs = []
    for inp in bch_tx['inputs']:
        inputs.append({
            'txid': inp['txid'],
            'index': inp['spent_index'],
            'address': inp['address'],
            'value': inp['value'],
            'token_data': inp['token_data'],
            'is_input': True,
        })

    outputs = []
    for out in bch_tx['outputs']:
        outputs.append({
            'txid': bch_tx['txid'],
            'index': out['index'],
            'address': out['address'],
            'value': out['value'],
            'token_data': out['token_data'],
            'is_input': False,
        })

    return inputs + outputs


def parse_utxo_to_tuple(data:dict, is_slp=False):
    """
        Should work for both input and output of tx data from BCHN/BCHD
    """
    if is_slp: return (data['address'], data['amount'])

    return (data['address'], data['value'], data['token_data'])
