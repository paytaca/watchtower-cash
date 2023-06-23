import logging
from functools import lru_cache
from bitcoinrpc.authproxy import AuthServiceProxy

from django.conf import settings
from django.utils import timezone

import socket
import time
import json


class BCHN(object):

    def __init__(self):
        self.max_retries = 20
        self.rpc_connection = AuthServiceProxy(settings.BCHN_NODE)
        self.source = 'bchn'
        self.fulcrum = {
            'host': settings.BCHN_HOST,
            'port': 60001
        }

    def get_latest_block(self):
        return self.rpc_connection.getblockcount()
        
    def get_block(self, block, verbosity=None):
        block_hash = self.rpc_connection.getblockhash(block)
        block_data = self.rpc_connection.getblock(block_hash, verbosity)
        return block_data['tx']

    def get_block_stats(self, block_number_or_hash, stats=None):
        """
            block_number_or_hash: (int | str) 
            stats: (None, List<str>) provide list of strings to return only a subset of stats
                See https://docs.bitcoincashnode.org/doc/json-rpc/getblockstats/ for valid values
        """
        return self.rpc_connection.getblockstats(block_number_or_hash, stats)

    # Cache to prevent multiple requests when parsing transaction in '._parse_transaction()'
    @lru_cache(maxsize=128)
    def _get_raw_transaction(self, txid):
        retries = 0
        while retries < self.max_retries:
            try:
                txn = self.rpc_connection.getrawtransaction(txid, 2)
                return txn
            except Exception as exception:
                retries += 1
                logging.exception(exception)
                if retries >= self.max_retries:
                    raise exception
                time.sleep(1)

    def get_transaction(self, tx_hash):
        retries = 0
        while retries < self.max_retries:
            try:
                txn = self._get_raw_transaction(tx_hash)
                if txn:
                    return self._parse_transaction(txn)
                break
            except Exception as exception:
                retries += 1
                logging.exception(exception)
                if retries >= self.max_retries:
                    raise exception
                time.sleep(1)

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
            if 'coinbase' in tx_input:
                transaction['inputs'].append(tx_input)
                continue

            input_txid = tx_input['txid']

            if 'prevout' in tx_input.keys():
                prevout = tx_input['prevout']
                value = prevout['value']
                input_token_data = None
                scriptPubKey = prevout['scriptPubKey']

                if 'address' in scriptPubKey.keys():
                    input_address = scriptPubKey['address']
                else:
                    # for multisig input prevouts (no address given on data)
                    input_address = self.get_input_address(input_txid, tx_input['vout'])

                if 'tokenData' in prevout.keys():
                    input_token_data = prevout['tokenData']
            else:
                value = int(float(tx_input['value'] * (10 ** 8)))
                input_token_data = self.get_input_token_data(input_txid, tx_input['vout'])
                input_address = self.get_input_address(input_txid, tx_input['vout'])
            input_txid = tx_input['txid']
            data = {
                'txid': input_txid,
                'spent_index': tx_input['vout'],
                'value': value,
                'token_data': input_token_data,
                'address': input_address
            }
            transaction['inputs'].append(data)

        transaction['outputs'] = []
        outputs = txn['vout']

        for tx_output in outputs:
            if 'value' in tx_output.keys() and 'addresses' in tx_output['scriptPubKey'].keys():
                sats_value = int(float(tx_output['value'] * (10 ** 8)))
                data = {
                    'address': tx_output['scriptPubKey']['addresses'][0],
                    'value': sats_value,
                    'index': tx_output['n'],
                    'token_data': None
                }
                if 'tokenData' in tx_output.keys():
                    data['token_data'] = tx_output['tokenData']
                transaction['outputs'].append(data)

        if 'fee' in txn:
            transaction['tx_fee'] = int(txn['fee'] * (10 ** 8))
        return transaction

    def broadcast_transaction(self, hex_str):
        retries = 0
        while retries < self.max_retries:
            try:
                return self.rpc_connection.sendrawtransaction(hex_str)
            except Exception as exception:
                retries += 1
                if retries >= self.max_retries:
                    raise exception
                time.sleep(1)
    
    def get_input_address(self, txid, vout_index):
        previous_tx = self._get_raw_transaction(txid)
        previous_out = previous_tx['vout'][vout_index]
        return previous_out['scriptPubKey']['addresses'][0]

    def get_input_token_data(self, txid, vout_index):
        previous_tx = self._get_raw_transaction(txid)
        previous_out = previous_tx['vout'][vout_index]

        if 'tokenData' in previous_out.keys():
            return previous_out['tokenData']
        return None
    
    def _recvall(self, sock):
        BUFF_SIZE = 4096
        data = bytearray()
        while True:
            packet = sock.recv(BUFF_SIZE)
            if not packet:  # Important!!
                break
            if len(packet) < BUFF_SIZE:
                data.extend(packet)
                break
            data.extend(packet)
        return data

    def get_utxos(self, address):
        data = '{ "id": 194, "method": "blockchain.address.listunspent",'
        data += '"params": ["%s", "include_tokens"] }' % (address)

        with socket.create_connection((
            self.fulcrum['host'],
            self.fulcrum['port']
        )) as sock:
            sock.send(data.encode('utf-8')+b'\n')
            response_byte = self._recvall(sock)
            response = response_byte.decode()
            response = json.loads(response.strip())
            return response['result']

    def get_input_address(self, txid, vout_index):
        previous_tx = self._get_raw_transaction(txid)
        previous_out = previous_tx['vout'][vout_index]
        return previous_out['scriptPubKey']['addresses'][0]

    def get_input_token_data(self, txid, vout_index):
        previous_tx = self._get_raw_transaction(txid)
        previous_out = previous_tx['vout'][vout_index]

        if 'tokenData' in previous_out.keys():
            return previous_out['tokenData']
        return None
