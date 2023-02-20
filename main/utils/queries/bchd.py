#!/usr/bin/env python3
import grpc
import random
import logging
from main.utils.bchd import bchrpc_pb2 as pb
from main.utils.bchd import bchrpc_pb2_grpc as bchrpc
from grpc._channel import _InactiveRpcError
import base64
import ssl

LOGGER = logging.getLogger(__name__)

class BCHDQuery(object):

    def __init__(self):
        nodes = [
            'bchd.paytaca.com:8335'
        ]
        self.base_url = random.choice(nodes)

        self._slp_action = {
            0: 'NON_SLP',
            1: 'NON_SLP_BURN',
            2: 'SLP_PARSE_ERROR',
            3: 'SLP_UNSUPPORTED_VERSION',
            4: 'SLP_V1_GENESIS',
            5: 'SLP_V1_MINT',
            6: 'SLP_V1_SEND',
            7: 'SLP_V1_NFT1_GROUP_GENESIS',
            8: 'SLP_V1_NFT1_GROUP_MINT',
            9: 'SLP_V1_NFT1_GROUP_SEND',
            10: 'SLP_V1_NFT1_UNIQUE_CHILD_GENESIS',
            11: 'SLP_V1_NFT1_UNIQUE_CHILD_SEND'
        }

    def get_latest_block(self, include_transactions=True, full_transactions=False):
        cert = ssl.get_server_certificate(self.base_url.split(':'))
        creds = grpc.ssl_channel_credentials(root_certificates=str.encode(cert))

        with grpc.secure_channel(self.base_url, creds, options=(('grpc.enable_http_proxy', 0),)) as channel:
            stub = bchrpc.bchrpcStub(channel)
            
            req = pb.GetBlockchainInfoRequest()
            resp = stub.GetBlockchainInfo(req)
            latest_block = resp.best_height

            return latest_block

    def get_block(self, block, full_transactions=False):
        cert = ssl.get_server_certificate(self.base_url.split(':'))
        creds = grpc.ssl_channel_credentials(root_certificates=str.encode(cert))

        with grpc.secure_channel(self.base_url, creds, options=(('grpc.enable_http_proxy', 0),)) as channel:
            stub = bchrpc.bchrpcStub(channel)

            req = pb.GetBlockRequest()
            req.height = block
            req.full_transactions = full_transactions
            resp = stub.GetBlock(req)

            return resp.block.transaction_data

    def _parse_transaction(self, txn, parse_slp=False):
        tx_hash = bytearray(txn.hash[::-1]).hex()
        transaction = {
            'txid': tx_hash,
            'timestamp': txn.timestamp,
            'valid': True
        }
        total_input_sats = 0
        total_output_sats = 0
        if parse_slp:
            is_valid = bool(txn.slp_transaction_info.validity_judgement)
            transaction['valid'] = is_valid
            transaction['token_id'] = txn.slp_transaction_info.token_id.hex()
            slp_action = txn.slp_transaction_info.slp_action
            transaction['slp_action'] = self._slp_action[slp_action]

            # If genesis tx, give more token metadata
            genesis_map = {
                4: 'v1_genesis',
                7: 'v1_genesis',
                10: 'nft1_child_genesis'
            }
            if slp_action in genesis_map.keys():
                genesis_info = eval('txn.slp_transaction_info.' + genesis_map[slp_action])
                try:
                    token_type = txn.outputs[1].slp_token.token_type
                except IndexError:
                    if slp_action == 4:
                        token_type = 1
                    elif slp_action == 7:
                        token_type = 129
                    elif slp_action == 10:
                        token_type = 65
                parent_group = None
                if token_type == 65:
                    parent_group = genesis_info.group_token_id.hex()
                transaction['token_info'] = {
                    'name': genesis_info.name.decode(),
                    'type': token_type,
                    'ticker': genesis_info.ticker.decode(),
                    'document_url': genesis_info.document_url.decode(),
                    'nft_token_group': parent_group,
                    'mint_amount': getattr(genesis_info, 'mint_amount', None),
                    'decimals': genesis_info.decimals or 0
                }
            
            transaction['inputs'] = []
            txid_spent_index_pairs = []
            if is_valid:
                transaction['token_id'] = txn.slp_transaction_info.token_id.hex()
                for tx_input in txn.inputs:
                    if tx_input.slp_token.token_id:
                        input_txid = tx_input.outpoint.hash[::-1].hex()
                        decimals = tx_input.slp_token.decimals or 0
                        amount = tx_input.slp_token.amount / (10 ** decimals)
                        data = {
                            'txid': input_txid,
                            'spent_index': tx_input.outpoint.index,
                            'amount': amount,
                            'address': 'simpleledger:' + tx_input.slp_token.address
                        }
                        transaction['inputs'].append(data)
                        txid_spent_index_pairs.append(f"{input_txid}-{tx_input.outpoint.index}")
                transaction['outputs'] = []
                output_index = 0
                for tx_output in txn.outputs:
                    total_output_sats += tx_output.value
                    if tx_output.slp_token.token_id:
                        decimals = tx_output.slp_token.decimals or 0
                        amount = tx_output.slp_token.amount / (10 ** decimals)
                        data = {
                            'address': 'simpleledger:' + tx_output.slp_token.address,
                            'amount': amount,
                            'index': output_index
                        }
                        transaction['outputs'].append(data)
                    output_index += 1

            # Valid or invalid, parse the inputs for marking of spent UTXOs and computation of tx fee
            for tx_input in txn.inputs:
                total_input_sats += tx_input.value
                input_txid = tx_input.outpoint.hash[::-1].hex()
                data = {
                    'txid': input_txid,
                    'spent_index': tx_input.outpoint.index,
                    'value': tx_input.value,
                    'address': 'bitcoincash:' + tx_input.address
                }
                txid_spent_index_pair = f"{input_txid}-{tx_input.outpoint.index}"
                if txid_spent_index_pair not in txid_spent_index_pairs:
                    transaction['inputs'].append(data)
                    txid_spent_index_pairs.append(txid_spent_index_pair)
        else:
            transaction['inputs'] = []
            for tx_input in txn.inputs:
                total_input_sats += tx_input.value
                input_txid = tx_input.outpoint.hash[::-1].hex()
                data = {
                    'txid': input_txid,
                    'spent_index': tx_input.outpoint.index,
                    'value': tx_input.value,
                    'address': 'bitcoincash:' + tx_input.address
                }
                transaction['inputs'].append(data)
            transaction['outputs'] = []
            output_index = 0
            for tx_output in txn.outputs:
                if tx_output.value is not None:
                    total_output_sats += tx_output.value
                if tx_output.address and tx_output.value:
                    data = {
                        'address': 'bitcoincash:' + tx_output.address,
                        'value': tx_output.value,
                        'index': output_index
                    }
                    transaction['outputs'].append(data)
                output_index += 1

        transaction['tx_fee'] =  total_input_sats - total_output_sats
        return transaction

    def _get_raw_transaction(self, transaction_hash):
        cert = ssl.get_server_certificate(self.base_url.split(':'))
        creds = grpc.ssl_channel_credentials(root_certificates=str.encode(cert))

        with grpc.secure_channel(self.base_url, creds, options=(('grpc.enable_http_proxy', 0),)) as channel:
            stub = bchrpc.bchrpcStub(channel)
            
            try:
                req = pb.GetTransactionRequest()
                txn_bytes = bytes.fromhex(transaction_hash)[::-1]
                req.hash = txn_bytes
                req.include_token_metadata = True

                resp = stub.GetTransaction(req)
                return resp.transaction
            except _InactiveRpcError as exc:
                LOGGER.error(str(exc))
                return None

    def get_transaction(self, transaction_hash, parse_slp=False):
        txn = self._get_raw_transaction(transaction_hash)
        if txn:
            return self._parse_transaction(txn, parse_slp=parse_slp)

    def get_utxos(self, address):
        cert = ssl.get_server_certificate(self.base_url.split(':'))
        creds = grpc.ssl_channel_credentials(root_certificates=str.encode(cert))

        with grpc.secure_channel(self.base_url, creds, options=(('grpc.enable_http_proxy', 0),)) as channel:
            stub = bchrpc.bchrpcStub(channel)

            req = pb.GetAddressUnspentOutputsRequest()
            req.address = address
            req.include_mempool = True
            resp = stub.GetAddressUnspentOutputs(req)
            return resp.outputs

    def get_transactions_count(self, blockheight):
        cert = ssl.get_server_certificate(self.base_url.split(':'))
        creds = grpc.ssl_channel_credentials(root_certificates=str.encode(cert))

        with grpc.secure_channel(self.base_url, creds, options=(('grpc.enable_http_proxy', 0),)) as channel:
            stub = bchrpc.bchrpcStub(channel)

            req = pb.GetBlockRequest()
            req.height = blockheight
            req.full_transactions = False
            resp = stub.GetBlock(req)

            trs = resp.block.transaction_data
            return len(trs)

    def get_address_transactions(self, address, limit=None, offset=None):
        cert = ssl.get_server_certificate(self.base_url.split(':'))
        creds = grpc.ssl_channel_credentials(root_certificates=str.encode(cert))

        with grpc.secure_channel(self.base_url, creds, options=(('grpc.enable_http_proxy', 0),)) as channel:
            stub = bchrpc.bchrpcStub(channel)

            req = pb.GetAddressTransactionsRequest()
            req.address = address
            if limit is not None:
                req.nb_fetch = limit
            if offset is not None:
                req.nb_skip = offset
            resp = stub.GetAddressTransactions(req)

            return resp

    def broadcast_transaction(self, transaction):
        txn_bytes = bytes.fromhex(transaction)
        cert = ssl.get_server_certificate(self.base_url.split(':'))
        creds = grpc.ssl_channel_credentials(root_certificates=str.encode(cert))

        with grpc.secure_channel(self.base_url, creds, options=(('grpc.enable_http_proxy', 0),)) as channel:
            stub = bchrpc.bchrpcStub(channel)

            req = pb.SubmitTransactionRequest()
            req.transaction = txn_bytes
            resp = stub.SubmitTransaction(req)

            tx_hash = bytearray(resp.hash[::-1]).hex()
            return tx_hash
