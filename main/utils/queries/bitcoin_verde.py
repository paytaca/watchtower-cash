from main.utils.address_converter import bch_to_slp_addr

import requests


class BitcoinVerde(object):
    
    def __init__(self):
        self.BASE_URL = 'https://explorer.bitcoinverde.org/api/v1'
        self.source = 'bitcoin-verde'

    def validate_transaction(self, txid):
        url = f'{self.BASE_URL}/slp/validate/{txid}'
        response = requests.get(url)
        result = response.json()
        
        if response.status_code == 200:
            return result['isValid']
        return False
    
    def get_transaction(self, txid):
        url = f'{self.BASE_URL}/search?query={txid}'
        response = requests.get(url)
        result = response.json()

        if response.status_code == 200:
            txn = response.json()
            object_type = txn['objectType']

            if object_type.lower() == 'transaction':
                return self.parse_transaction(txn['object'])
        return None
    
    def parse_transaction(self, txn):
        txid = txn['hash']
        token_data = txn['slp']
        transaction = {
            'txid': txid,
            # 'timestamp': None,
            'valid': True,
            'inputs': [],
            'outputs': []
        }
        
        # PARSE TOKEN METADATA
        
        transaction['token_id'] = token_data['tokenId']
        # transaction['slp_action'] = 
        
        decimals = token_data['decimalCount']
        transaction['token_info'] = {
            'name': token_data['tokenName'],
            'type': None, # TODO: where to fetch this data?
            'ticker': token_data['tokenAbbreviation'],
            'document_url': token_data['documentUrl'],
            'document_hash': token_data['documentHash'],
            'nft_token_group': None, # TODO: where to fetch this data?
            'mint_amount': int(token_data['tokenCount']),
            'decimals': decimals,
            'mint_baton_index': token_data['batonIndex']
        }

        txid_spent_index_pairs = []


        # PARSE INPUTS

        for tx_input in txn['inputs']:
            if 'slp' in tx_input.keys():
                input_txid = tx_input['previousOutputTransactionHash']
                index = tx_input['previousOutputIndex']

                slp_data = tx_input['slp']
                amount = slp_data['tokenAmount'] / (10 ** decimals)
                address = tx_input['cashAddress']
                slp_address = bch_to_slp_addr(address)

                data = {
                    'txid': input_txid,
                    'spent_index': index,
                    'amount': amount,
                    'address': slp_address
                }
                transaction['inputs'].append(data)
                txid_spent_index_pairs.append(f'{input_txid}-{index}')
        

        # PARSE OUTPUTS

        for tx_output in txn['outputs']:
            if 'slp' in tx_output.keys():
                slp_data = tx_output['slp']
                amount = slp_data['tokenAmount'] /  (10 ** decimals)
                data = {
                    'address': bch_to_slp_addr(tx_output['cashAddress']),
                    'amount': amount,
                    'index': tx_output['index']
                }

                if slp_data['isBaton']:
                    data['is_mint_baton'] = True
                
                transaction['outputs'].append(data)


        # Parse the non-token inputs for marking of spent utxos
        for tx_input in txn['inputs']:
            value = tx_input['previousTransactionAmount']
            input_txid = tx_input['previousOutputTransactionHash']
            index = tx_input['previousOutputIndex']
            data = {
                'txid': input_txid,
                'spent_index': index,
                'value': value,
                'address': tx_input['cashAddress']
            }
            txid_spent_index_pair = f'{input_txid}-{index}'
            if txid_spent_index_pair not in txid_spent_index_pairs:
                transaction['inputs'].append(data)
                txid_spent_index_pairs.append(txid_spent_index_pair)


        transaction['tx_fee'] = txn['fee']
        return transaction
