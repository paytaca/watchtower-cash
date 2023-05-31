from main.utils.address_converter import bch_to_slp_addr
from main.utils.queries.bchn import BCHN

import requests


class BitcoinVerde(object):
    
    def __init__(self):
        self.BASE_URL = 'https://explorer.bitcoinverde.org/api/v1'
        self.source = 'bitcoin-verde'

    def validate_transaction(self, txid):
        url = f'{self.BASE_URL}/slp/validate/{txid}'
        response = requests.get(url)
        
        if response.status_code == 200:
            result = response.json()

            if result['wasSuccess']:
                return result['isValid']
        return False
    
    def get_transaction(self, txid):
        url = f'{self.BASE_URL}/search?query={txid}'
        response = requests.get(url)

        if response.status_code == 200:
            result = response.json()

            if result['wasSuccess']:
                txn = response.json()
                object_type = txn['objectType']

                if object_type.lower() == 'transaction':
                    return self.parse_transaction(txn['object'])
        return None
    
    def parse_transaction(self, txn):
        txid = txn['hash']
        token_data = txn['slp']
        block_hash = txn['blocks'][0]
        block = self.get_block(block_hash)
        timestamp = block['timestamp']['value']

        transaction = {
            'txid': txid,
            'timestamp': timestamp,
            'valid': True,
            'inputs': [],
            'outputs': []
        }
        
        # PARSE TOKEN METADATA
        
        transaction['token_id'] = token_data['tokenId']
        decimals = token_data['decimalCount']
        
        transaction['token_info'] = {
            'name': token_data['tokenName'],
            'type': None, # TODO: check where this data can be fetched
            'ticker': token_data['tokenAbbreviation'],
            'document_url': token_data['documentUrl'],
            'document_hash': token_data['documentHash'],
            'nft_token_group': None, # TODO: check where this data can be fetched
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

    def get_block(self, block_hash):
        url = f'{self.BASE_URL}/search?query={block_hash}'
        response = requests.get(url)

        if response.status_code == 200:
            result = response.json()

            if result['wasSuccess']:
                return result['object']
        return None

    def get_utxos(self, address):
        url = f'{self.BASE_URL}/search?query={address}'
        response = requests.get(url)
        utxos = []

        if response.status_code == 200:
            result = response.json()

            if result['wasSuccess']:
                transactions = result['object']['transactions']

                for txn in transactions:
                    txid = txn['hash']

                    if self.validate_transaction(txid):
                        for output in txn['outputs']:
                            if output['spentByTransaction'] is not None:
                                if 'slp' in output.keys():
                                    index = output['index']
                                    amount = output['slp']['tokenAmount']
                                    token_id = output['slp']['tokenId']
                                    value = output['amount']
                                    block_hash = txn['blocks'][0]

                                    block = self.get_block(block_hash)
                                    height = block['height']

                                    utxos.append({
                                        'token_id': token_id,
                                        'index': index,
                                        'amount': amount,
                                        'value': value,
                                        'tx_hash': txid,
                                        'height': height
                                    })

        return utxos
