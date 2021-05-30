#!/usr/bin/env python3
import grpc
import random
import logging
from main.utils.bchd import bchrpc_pb2 as pb
from main.utils.bchd import bchrpc_pb2_grpc as bchrpc

LOGGER = logging.getLogger(__name__)

class BCHDQuery(object):

    def __init__(self):
        nodes = [
            'bchd.imaginary.cash:8335',
            'bchd.ny1.simpleledger.io:8335',
            'bchd.greyh.at:8335'
        ]
        self.base_url = random.choice(nodes)

    def get_latest_block(self):
        creds = grpc.ssl_channel_credentials()

        with grpc.secure_channel(self.base_url, creds) as channel:
            stub = bchrpc.bchrpcStub(channel)
            
            req = pb.GetBlockchainInfoRequest()
            resp = stub.GetBlockchainInfo(req)
            latest_block = resp.best_height

            req = pb.GetBlockRequest()
            req.height = latest_block
            req.full_transactions = False
            resp = stub.GetBlock(req)

            return latest_block, resp.block.transaction_data

    def get_raw_transaction(self, transaction_hash):
        creds = grpc.ssl_channel_credentials()

        with grpc.secure_channel(self.base_url, creds) as channel:
            stub = bchrpc.bchrpcStub(channel)

            req = pb.GetTransactionRequest()
            req.hash = transaction_hash

            resp = stub.GetTransaction(req)
            return resp.transaction

    def get_utxos(self, address):
        creds = grpc.ssl_channel_credentials()

        with grpc.secure_channel(self.base_url, creds) as channel:
            stub = bchrpc.bchrpcStub(channel)

            req = pb.GetAddressUnspentOutputsRequest()
            req.address = address
            req.include_mempool = True
            resp = stub.GetAddressUnspentOutputs(req)
            return resp.outputs

    def get_transactions_count(self, blockheight):
        creds = grpc.ssl_channel_credentials()

        with grpc.secure_channel(self.base_url, creds) as channel:
            stub = bchrpc.bchrpcStub(channel)

            req = pb.GetBlockRequest()
            req.height = blockheight
            req.full_transactions = False
            resp = stub.GetBlock(req)

            trs = resp.block.transaction_data
            return len(trs)

    def broadcast_transaction(self, transaction):
        txn_bytes = bytes.fromhex(transaction)
        creds = grpc.ssl_channel_credentials()

        with grpc.secure_channel(self.base_url, creds) as channel:
            stub = bchrpc.bchrpcStub(channel)

            req = pb.SubmitTransactionRequest()
            req.transaction = txn_bytes
            resp = stub.SubmitTransaction(req)

            tx_hash = bytearray(resp.hash[::-1]).hex()
            return tx_hash
