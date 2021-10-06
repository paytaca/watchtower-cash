from django.core.management.base import BaseCommand
from main.utils.bchd import bchrpc_pb2 as pb
from main.utils.bchd import bchrpc_pb2_grpc as bchrpc
from main.models import Token, Transaction
import grpc
import time
import random
import logging
import ssl
from main.tasks import save_record, client_acknowledgement, send_telegram_message

LOGGER = logging.getLogger(__name__)



def run():
    source = 'bchd-grpc-stream'
    nodes = [
        'bchd.imaginary.cash:8335',
        'bchd.greyh.at:8335',
        # 'bchd.fountainhead.cash:443'
    ]
    bchd_node = random.choice(nodes)

    cert = ssl.get_server_certificate(bchd_node.split(':'))
    creds = grpc.ssl_channel_credentials(root_certificates=str.encode(cert))

    with grpc.secure_channel(bchd_node, creds, options=(('grpc.enable_http_proxy', 0),)) as channel:
        stub = bchrpc.bchrpcStub(channel)

        req = pb.GetBlockchainInfoRequest()
        resp = stub.GetBlockchainInfo(req)
        tx_filter = pb.TransactionFilter()
        tx_filter.all_transactions = True

        req = pb.SubscribeTransactionsRequest()
        req.include_mempool = True
        req.include_in_block = False
        req.subscribe.CopyFrom(tx_filter)

        for notification in stub.SubscribeTransactions(req):
            tx = notification.unconfirmed_transaction.transaction
            tx_hash = bytearray(tx.hash[::-1]).hex()

            for _input in tx.inputs:
                
                txid = _input.outpoint.hash.hex()
                index = _input.outpoint.index

            for output in tx.outputs:
                if output.address:
                    bchaddress = 'bitcoincash:' + output.address
                    amount = output.value / (10 ** 8)
                    args = (
                        'bch',
                        bchaddress,
                        tx_hash,
                        amount,
                        source,
                        None,
                        output.index
                    )
                    obj_id, created = save_record(*args)
                    if created:
                        third_parties = client_acknowledgement(obj_id)
                        for platform in third_parties:
                            if 'telegram' in platform:
                                message = platform[1]
                                chat_id = platform[2]
                                send_telegram_message(message, chat_id)
                    msg = f"{source}: {tx_hash} | {bchaddress} | {amount} "
                    LOGGER.info(msg)

                if output.slp_token.token_id:
                    token_id = bytearray(output.slp_token.token_id).hex() 
                    amount = output.slp_token.amount / (10 ** output.slp_token.decimals)
                    slp_address = 'simpleledger:' + output.slp_token.address
                    args = (
                        token_id,
                        slp_address,
                        tx_hash,
                        amount,
                        source,
                        None,
                        output.index
                    )
                    obj_id, created = save_record(*args)

                    if created:
                        third_parties = client_acknowledgement(obj_id)
                        for platform in third_parties:
                            if 'telegram' in platform:
                                message = platform[1]
                                chat_id = platform[2]
                                send_telegram_message(message, chat_id)
                    msg = f"{source}: {tx_hash} | {slp_address} | {amount} | {token_id}"
                    LOGGER.info(msg)


class Command(BaseCommand):
    help = "Run the mempool tracker using BCHD GRPC stream"

    def handle(self, *args, **options):
        run()
