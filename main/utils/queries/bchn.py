from bitcoinrpc.authproxy import AuthServiceProxy

from django.conf import settings


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
        transaction = {
            'txid': tx_hash,
            'timestamp': txn['time'],
            'valid': True
        }
        total_input_sats = 0
        total_output_sats = 0
        transaction['inputs'] = []

        for tx_input in txn['vin']:
            value = tx_input['value'] ** (10 ** 8)
            total_input_sats += value
            input_txid = tx_input['txid']

            ancestor_tx = self._get_raw_transaction(input_txid)
            ancestor_spubkey = ancestor_tx['vout'][tx_input['vout']]['scriptPubKey']

            data = {
                'txid': input_txid,
                'spent_index': len(ancestor_tx['vout']) - 1,
                'value': value,
                'address': ancestor_spubkey['addresses'][0]
            }
            transaction['inputs'].append(data)

        transaction['outputs'] = []
        outputs = txn['vout']
        output_index = 0

        for tx_output in outputs:
            if 'value' in tx_output.keys() and 'addresses' in tx_output['scriptPubKey'].keys():
                sats_value = tx_output['value'] ** (10 ** 8)
                data = {
                    'address': tx_output['addresses'],
                    'value': sats_value,
                    'index': output_index
                }
                transaction['outputs'].append(data)
            output_index += 1

        transaction['tx_fee'] = txn['fee'] ** (10 ** 8)
        return transaction

    def broadcast_transaction(self, hex_str):
        return self.rpc_connection.sendrawtransaction(hex_str)
