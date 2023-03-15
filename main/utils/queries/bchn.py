from bitcoinrpc.authproxy import AuthServiceProxy

from django.conf import settings
from django.utils import timezone


class BCHN(object):

    def __init__(self):
        url = f"http://{settings.RPC_USER}:{settings.RPC_PASSWORD}@docker-host:8332"
        self.rpc_connection = AuthServiceProxy(url)
        self.source = 'bchn'

    def get_latest_block(self):
        return self.rpc_connection.getblockcount()
        
    def get_block(self, block):
        block_hash = self.rpc_connection.getblockhash(block)
        block_data = self.rpc_connection.getblock(block_hash)
        return block_data['tx']

    def _get_raw_transaction(self, txid):
        return self.rpc_connection.getrawtransaction(txid, 2)

    def get_transaction(self, tx_hash):
        txn = self._get_raw_transaction(tx_hash)
        if txn:
            return self._parse_transaction(txn)

    def _parse_transaction(self, txn):
        tx_hash = txn['hash']
        
        # NOTE: very new transactions doesnt have timestamp
        time = timezone.now().timestamp()
        if 'time' in txn.keys():
            time = txn['time']

        transaction = {
            'txid': tx_hash,
            'timestamp': time,
            'valid': True
        }
        transaction['inputs'] = []

        for tx_input in txn['vin']:
            value = tx_input['value'] ** (10 ** 8)
            input_txid = tx_input['txid']
            data = {
                'txid': input_txid,
                'spent_index': tx_input['vout'],
                'value': value,
                'address': self.get_input_address(input_txid, tx_input['vout'])
            }
            transaction['inputs'].append(data)

        transaction['outputs'] = []
        outputs = txn['vout']

        for tx_output in outputs:
            if 'value' in tx_output.keys() and 'addresses' in tx_output['scriptPubKey'].keys():
                sats_value = tx_output['value'] ** (10 ** 8)
                data = {
                    'address': tx_output['scriptPubKey']['addresses'][0],
                    'value': sats_value,
                    'index': tx_output['n']
                }
                if 'tokenData' in tx_output.keys():
                    data['tokenData'] = tx_output['tokenData']
                transaction['outputs'].append(data)

        transaction['tx_fee'] = txn['fee'] ** (10 ** 8)
        return transaction

    def broadcast_transaction(self, hex_str):
        return self.rpc_connection.sendrawtransaction(hex_str)
    
    def get_input_address(self, txid, vout_index):
        previous_tx = self._get_raw_transaction(txid)
        previous_out = previous_tx['vout'][vout_index]
        return previous_out['scriptPubKey']['addresses'][0]