from main.utils.address_converter import bch_to_slp_addr
from main.utils.queries.bchn import BCHN
from main.utils.slp import *

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
        
        bcv_slp_data = txn['slp']
        token_id = bcv_slp_data['tokenId'].lower()
        token_data = get_slp_token_details(token_id)
        token_data = token_data['genesisData']
        token_type = token_data['type']

        transaction['token_id'] = token_id
        transaction['token_info'] = {
            'name': token_data['name'],
            'type': token_type,
            'ticker': token_data['ticker'],
            'document_url': token_data['documentUri'],
            'document_hash': token_data['documentHash'],
            'mint_amount': int(token_data['totalMinted']),
            'decimals': token_data['decimals']
        }

        # mint_baton_index = bcv_slp_data['batonIndex']
        # if mint_baton_index:
        #     transaction['token_info']['mint_baton_index'] = mint_baton_index
        if token_type in [65, 129]:
            transaction['token_info']['nft_token_group'] = token_data['parentGroupId']

        txid_spent_index_pairs = []


        # PARSE INPUTS

        for tx_input in txn['inputs']:
            if 'slp' in tx_input.keys():
                input_txid = tx_input['previousOutputTransactionHash']
                value = tx_input['previousTransactionAmount']
                index = tx_input['previousOutputIndex']

                slp_data = tx_input['slp']
                amount = slp_data['tokenAmount'] / (10 ** decimals)
                address = tx_input['cashAddress']
                slp_address = bch_to_slp_addr(address)

                data = {
                    'txid': input_txid,
                    'spent_index': index,
                    'amount': amount,
                    'address': slp_address,
                    'value': value
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
                    'index': tx_output['index'],
                    'value': tx_output['amount']
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
                    txid = txn['hash'].lower()

                    if self.validate_transaction(txid):
                        for output in txn['outputs']:
                            if output['spentByTransaction'] is None:
                                if 'slp' in output.keys():
                                    index = output['index']
                                    amount = output['slp']['tokenAmount']
                                    token_id = txn['slp']['tokenId'].lower()
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



bcv = BitcoinVerde()
bcv.get_transaction('09398369a40862003ca17e47928e791633801c29befd538b3dd5b2e5e100e92f')
