from django.core.management.base import BaseCommand
from django.conf import settings
from main.utils.bchd import bchrpc_pb2 as pb
from main.utils.bchd import bchrpc_pb2_grpc as bchrpc
from main.utils import check_wallet_address_subscription
from main.models import Token, Transaction
from main.tasks import save_record
import grpc
import time
import logging
import json

REDIS_STORAGE = settings.REDISKV

LOGGER = logging.getLogger(__name__)

if 'BCHD' not in REDIS_STORAGE.keys(): REDIS_STORAGE.set('BCHD', json.dumps([]))

def run():
    source = 'bchd_grpc_stream'
    creds = grpc.ssl_channel_credentials()
    with grpc.secure_channel('bchd.ny1.simpleledger.io', creds) as channel:
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

            for output in tx.outputs:
                if output.address:
                    bchaddress = 'bitcoincash:' + output.address
                    amount = output.value / (10 ** 8)

                    subscription = check_wallet_address_subscription(bchaddress)
                    # Disregard bch address that are not subscribed.
                    if subscription.exists():

                        txn_qs = Transaction.objects.filter(
                            address=bchaddress,
                            txid=tx_hash,
                            spent_index=output.index
                        )
                        if not txn_qs.exists():
                            args = (
                                'bch',
                                bchaddress,
                                tx_hash,
                                amount,
                                source,
                                None,
                                output.index
                            )
                            # save_record(*args)
                            
                            bchd = json.loads(REDIS_STORAGE.get('BCHD'))
                            bchd.append(args)
                            REDIS_STORAGE.set('BCHD', json.dumps(bchd))
                    
                    msg = f"{source}: {tx_hash} | {bchaddress} | {amount} "
                    LOGGER.info(msg)

                if output.slp_token.token_id:
                    token_id = bytearray(output.slp_token.token_id).hex() 
                    amount = output.slp_token.amount / (10 ** output.slp_token.decimals)
                    slp_address = 'simpleledger:' + output.slp_token.address

                    subscription = check_wallet_address_subscription(slp_address)
                    # Disregard slp address that are not subscribed.
                    if subscription.exists():
                        token, _ = Token.objects.get_or_create(tokenid=token_id)
                        txn_qs = Transaction.objects.filter(
                            address=slp_address,
                            txid=tx_hash,
                            spent_index=output.index
                        )
                        if not txn_qs.exists():
                            args = (
                                token.tokenid,
                                slp_address,
                                tx_hash,
                                amount,
                                source,
                                None,
                                output.index
                            )
                            # save_record(*args)
                            bchd = json.loads(REDIS_STORAGE.get('BCHD'))
                            bchd.append(args)
                            REDIS_STORAGE.set('BCHD', json.dumps(bchd))
                    
                    msg = f"{source}: {tx_hash} | {slp_address} | {amount} | {token_id}"
                    LOGGER.info(msg)


class Command(BaseCommand):
    help = "Run the tracker of bchd.ny1.simpleledger.io"

    def handle(self, *args, **options):
        run()
