import logging
from functools import lru_cache
from bitcoinrpc.authproxy import AuthServiceProxy

from django.conf import settings
from django.utils import timezone
import math
import socket
import time
import json
from functools import wraps

# Connect to Redis
redis_client = settings.REDISKV

def redis_cache(expiration_seconds=3600):  # Add expiration as a parameter
    def decorator(func):
        @wraps(func)
        def wrapper(*args):
            key = f"{func.__name__}:{args}"
            cached_value = redis_client.get(key)
            
            if cached_value:
                return json.loads(cached_value)  # Return cached value
            
            result = func(*args)  # Call the function if not cached
            redis_client.set(key, json.dumps(result), ex=expiration_seconds)  # Auto-expire after X seconds
            return result
        return wrapper
    return decorator


def retry(max_retries):
    def decorator_retry(func):
        def wrapper_retry(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as exception:
                    retries += 1
                    if retries >= max_retries:
                        raise exception
                    time.sleep(1)
        return wrapper_retry
    return decorator_retry


class BCHN(object):

    def __init__(self):
        self.max_retries = 20
        self.rpc_connection = AuthServiceProxy(settings.BCHN_NODE, timeout=30)
        self.source = 'bchn'
        self.fulcrum = {
            'host': settings.BCHN_HOST,
            'port': settings.FULCRUM_PORT
        }

    @retry(max_retries=3)
    def get_latest_block(self):
        return self.rpc_connection.getblockcount()

    @retry(max_retries=3)
    def get_block_chain_info(self):
        return self.rpc_connection.getblockchaininfo()

    @retry(max_retries=3)
    def get_block(self, block, verbosity=None):
        block_hash = self.rpc_connection.getblockhash(block)
        block_data = self.rpc_connection.getblock(block_hash, verbosity)
        return block_data['tx']

    @retry(max_retries=3)
    def get_block_stats(self, block_number_or_hash, stats=None):
        """
            block_number_or_hash: (int | str) 
            stats: (None, List<str>) provide list of strings to return only a subset of stats
                See https://docs.bitcoincashnode.org/doc/json-rpc/getblockstats/ for valid values
        """
        return self.rpc_connection.getblockstats(block_number_or_hash, stats)

    # Cache to prevent multiple requests when parsing transaction in '._parse_transaction()'
    @redis_cache(expiration_seconds=900)
    def _get_raw_transaction(self, txid):
        retries = 0
        while retries < self.max_retries:
            try:
                txn = self.rpc_connection.getrawtransaction(txid, 2)
                return txn
            except Exception as exception:
                retries += 1
                if retries >= self.max_retries:
                    if 'No such mempool or blockchain transaction' in str(exception):
                        break
                    else:
                        logging.exception(f'ERROR IN FETCHING TXN DETAILS: {txid}', exception)
                        raise exception
                time.sleep(1)

    @retry(max_retries=3)
    def _decode_raw_transaction(self, tx_hex):
        txn = self.rpc_connection.decoderawtransaction(tx_hex)
        return txn

    def build_tx_from_hex(self, tx_hex, tx_fee=None):
        txn = self._decode_raw_transaction(tx_hex)
        if not tx_fee:
            tx_fee = math.ceil(txn['size'] * settings.TX_FEE_RATE)
        for i, tx_input in enumerate(txn['vin']):
            _input_details = self.get_input_details(tx_input['txid'], tx_input['vout'])

            if 'value' in _input_details:
                txn['vin'][i]['value'] = _input_details['value'] / 10 ** 8

            if 'address' in _input_details:
                txn['vin'][i]['address'] = _input_details['address']

        txn['tx_fee'] = tx_fee
        txn['timestamp'] = None
        return txn

    @retry(max_retries=3)
    def get_transaction(self, tx_hash, include_hex=False, include_no_address=False):
        txn = self._get_raw_transaction(tx_hash)
        if txn:
            return self._parse_transaction(txn, include_hex=include_hex, include_no_address=include_no_address)

    def _parse_transaction(self, txn, include_hex=False, include_no_address=False):
        tx_hash = txn['hash']
        
        # NOTE: very new transactions doesnt have timestamp
        time = timezone.now().timestamp()
        if 'time' in txn.keys():
            time = txn['time']

        transaction = {
            'txid': tx_hash,
            'timestamp': time,
            'size': txn['size'],
            'confirmations': txn.get('confirmations'),
            'valid': True
        }

        if include_hex:
            transaction["hex"] = txn["hex"]

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
                    _input_details = self.get_input_details(input_txid, tx_input['vout'])
                    # for multisig input prevouts (no address given on data)
                    input_address = _input_details.get('address')

                if 'tokenData' in prevout.keys():
                    input_token_data = prevout['tokenData']
            else:
                _input_details = self.get_input_details(input_txid, tx_input['vout'])
                value = _input_details.get('value')
                input_token_data = _input_details.get('token_data')
                input_address = _input_details.get('address')

            if not include_no_address and not input_address:
                continue

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
            data = self._parse_output(tx_output)
            if not include_no_address and not data.get('address'):
                continue
            transaction['outputs'].append(data)

        if 'fee' in txn:
            transaction['tx_fee'] = round(txn['fee'] * (10 ** 8))
        return transaction

    def _parse_output(self, tx_output):
        details = {
            'index': tx_output['n'],
            'token_data': None,
        }
        if 'value' in tx_output.keys():
            details['value'] = round(tx_output['value'] * (10 ** 8))
            
        if 'scriptPubKey' in tx_output.keys():
            script_pubkey = tx_output['scriptPubKey']
            if 'addresses' in script_pubkey.keys():
                details['address'] = script_pubkey['addresses'][0]
            elif script_pubkey.get('type') == 'nulldata':
                # remove first characters '6a'
                details['op_return'] = script_pubkey['hex'][:2]
            else:
                details['script'] = script_pubkey.get('hex')

        if 'tokenData' in tx_output.keys():
            details['token_data'] = tx_output['tokenData']

        return details

    @retry(max_retries=3)
    def test_mempool_accept(self, hex_str):
        return self.rpc_connection.testmempoolaccept([hex_str])[0]

    @retry(max_retries=3)  
    def broadcast_transaction(self, hex_str):
        return self.rpc_connection.sendrawtransaction(hex_str)
    
    def get_input_details(self, txid, vout_index):
        previous_tx = self._get_raw_transaction(txid)
        if previous_tx:
            previous_out = previous_tx['vout'][vout_index]
            return self._parse_output(previous_out)
    
    def _recvall(self, sock):
        BUFF_SIZE = 4096
        data = bytearray()
        while True:
            packet = sock.recv(BUFF_SIZE)
            data.extend(packet)
            if data.endswith(bytes('\r\n', 'utf-8')):
                break
        return data

    def get_utxos(self, address):
        data = '{ "id": 0, "method": "blockchain.address.listunspent",'
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
        
    def get_address_transactions(self, address, limit=None, offset=None):
        data = '{ "id": 0, "method": "blockchain.address.get_history",'
        data += '"params": ["%s"] }' % (address)

        with socket.create_connection((
            self.fulcrum['host'],
            self.fulcrum['port']
        )) as sock:
            sock.send(data.encode('utf-8')+b'\n')
            response_byte = self._recvall(sock)
            response = response_byte.decode()
            response = json.loads(response.strip())
            return response['result']

    def get_dsproof(self, identifier, limit=None, offset=None):
        """
        identifier: (str) tx hash or dsproof ID
        """
        data = '{ "id": 0, "method": "blockchain.transaction.dsproof.get",'
        data += '"params": ["%s"] }' % (identifier)

        with socket.create_connection((
            self.fulcrum['host'],
            self.fulcrum['port']
        )) as sock:
            sock.send(data.encode('utf-8')+b'\n')
            response_byte = self._recvall(sock)
            response = response_byte.decode()
            response = json.loads(response.strip())
            return response['result']

    def get_fulcrum_server_features(self, limit=None, offset=None):
        data = '{ "id": 0, "method": "server.features" }'

        with socket.create_connection((
            self.fulcrum['host'],
            self.fulcrum['port']
        )) as sock:
            sock.send(data.encode('utf-8')+b'\n')
            response_byte = self._recvall(sock)
            response = response_byte.decode()
            response = json.loads(response.strip())
            return response['result']