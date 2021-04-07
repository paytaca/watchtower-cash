#!/usr/bin/env python3
import grpc
import logging
from main.utils.bchd import bchrpc_pb2 as pb
from main.utils.bchd import bchrpc_pb2_grpc as bchrpc

LOGGER = logging.getLogger(__name__)

class BCHDQuery(object):

    def __init__(self):
        self.base_url = 'bchd.ny1.simpleledger.io'


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



    def get_transactions_count(self, blockheight):
        creds = grpc.ssl_channel_credentials()

        with grpc.secure_channel(self.base_url, creds) as channel:
            stub = bchrpc.bchrpcStub(channel)

            req = pb.GetBlockRequest()
            req.height = blockheight
            req.full_transactions = False
            resp = stub.GetBlock(req)

            trs =  resp.block.transaction_data
            return len(trs)