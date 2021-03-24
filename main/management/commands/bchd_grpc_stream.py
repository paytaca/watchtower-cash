from django.core.management.base import BaseCommand
from main.utils.bchd import bchrpc_pb2 as pb
from main.utils.bchd import bchrpc_pb2_grpc as bchrpc
from main.utils import check_wallet_address_subscription
from main.models import Token, Transaction
from main.tasks import save_record
import grpc
import time
import logging

LOGGER = logging.getLogger(__name__)


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
            has_op_return_data = False

            for output in tx.outputs:
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
                        save_record(*args)
                msg = f"{source}: {tx_hash} | {bchaddress} | {amount} "
                LOGGER.info(msg)

                if output.script_class == 'datacarrier':
                    has_op_return_data = True
                
                if has_op_return_data:
                    if output.slp_token.token_id:
                        token_id = bytearray(output.slp_token.token_id).hex() 
                        amount = output.slp_token.amount / (10 ** output.slp_token.decimals)
                        slp_address = 'simpleledger:' + output.slp_token.address

                        subscription = check_wallet_address_subscription(slp_address)
                        # Disregard bch address that are not subscribed.
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
                                save_record(*args)
                        msg = f"{source}: {tx_hash} | {slp_address} | {amount} | {token_id}"
                        LOGGER.info(msg)


class Command(BaseCommand):
    help = "Run the tracker of bchd.ny1.simpleledger.io"

    def handle(self, *args, **options):
        run()
