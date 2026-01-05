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
        if not out.get('address'):
            continue

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


def flatten_output_data(output_data:dict):
    """
        Flatten output details needed for transaction processing
        output_data should be the same as BCHN._parse_output() data structure

        returns tuple(index, address, satoshis, category, token_units, capability, commitment)
    """
    address = output_data.get("address")
    index = output_data['index']
    value = output_data['value']  # Already in satoshis from _parse_output

    token_data_tuple = flatten_token_data(output_data.get("token_data"))
    return (index, address, value, *token_data_tuple)


def flatten_token_data(output_token_data:dict):
    if not isinstance(output_token_data, dict) or "category" not in output_token_data:
        return (None, None, None, None)
    
    category = output_token_data["category"]
    token_units = output_token_data.get("amount")
    capability = None
    commitment = None
    if isinstance(output_token_data.get("nft"), dict):
        capability = output_token_data["nft"].get("capability")
        commitment = output_token_data["nft"].get("commitment")

    return (category, token_units, capability, commitment)
