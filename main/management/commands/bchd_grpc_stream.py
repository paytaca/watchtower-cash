from django.conf import settings
from django.utils import timezone as tz
from django.core.management.base import BaseCommand
from main.utils.bchd import bchrpc_pb2 as pb
from main.utils.bchd import bchrpc_pb2_grpc as bchrpc
from main.models import Token, Transaction, Subscription
import grpc
import json
import logging
import ssl
from main.tasks import (
    save_record,
    client_acknowledgement,
    send_telegram_message,
    parse_tx_wallet_histories,
)
import paho.mqtt.client as mqtt


mqtt_client = mqtt.Client()
mqtt_client.connect("docker-host", 1883, 10)
mqtt_client.loop_start()


# Logger
LOGGER = logging.getLogger(__name__)


def run():
    source = 'bchd-grpc-stream'
    bchd_node = settings.BCHD_NODE

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
            now = tz.now().timestamp()
            tx = notification.unconfirmed_transaction.transaction
            tx_hash = bytearray(tx.hash[::-1]).hex()

            has_subscribed_input = False
            has_updated_output = False

            # inputs_added = False
            inputs_data = [
                # { "index": 0, "token": "bch", "address": "", "amount": 0,  "outpoint_txid": "", "outpoint_index": 0 }
            ]
            for _input in tx.inputs:
                txid = bytearray(_input.outpoint.hash[::-1]).hex()
                index = _input.outpoint.index
                spent_transactions = Transaction.objects.filter(txid=txid, index=index)
                
                spent_transactions.update(spent=True, spending_txid=tx_hash)
                has_existing_wallet = spent_transactions.filter(wallet__isnull=False).exists()
                has_subscribed_input = has_subscribed_input or has_existing_wallet

                token_id = None
                address = None
                amount = None
                value = 0
                if _input.slp_token.token_id:
                    token_id = bytearray(_input.slp_token.token_id).hex() 
                    address = 'simpleledger:' + _input.address
                    amount = output.slp_token.amount
                else:
                    token_id = "bch"
                    address = 'bitcoincash:' + _input.address
                    value = _input.value


                subscription = Subscription.objects.filter(
                    address__address=address             
                )

                if token_id and subscription.exists():
                    inputs_data.append({
                        "index": _input.index,
                        "token": token_id,
                        "address": address,
                        "amount": amount,
                        "value": value,
                        "outpoint_txid": txid,
                        "outpoint_index": index,
                    })

            for output in tx.outputs:
                if output.address:
                    bchaddress = 'bitcoincash:' + output.address
                    amount = output.value / (10 ** 8)
                    args = (
                        'bch',
                        bchaddress,
                        tx_hash,
                        source
                    )
                    obj_id, created = save_record(
                        *args,
                        value=value,
                        blockheightid=None,
                        index=output.index,
                        inputs=inputs_data,
                        tx_timestamp=now
                    )
                    has_updated_output = has_updated_output or created

                    if created:
                        # Publish MQTT message
                        data = {
                            'txid': tx_hash,
                            'recipient': bchaddress,
                            'amount': amount
                        }
                        LOGGER.info('Sending MQTT message: ' + str(data))
                        msg = mqtt_client.publish(f"transactions/{bchaddress}", json.dumps(data), qos=1)
                        LOGGER.info('MQTT message is published: ' + str(msg.is_published()))

                        client_acknowledgement(obj_id)

                    msg = f"{source}: {tx_hash} | {bchaddress} | {amount} "
                    LOGGER.info(msg)

                if output.slp_token.token_id:
                    token_id = bytearray(output.slp_token.token_id).hex() 
                    amount = output.slp_token.amount
                    slp_address = 'simpleledger:' + output.slp_token.address
                    args = (
                        token_id,
                        slp_address,
                        tx_hash,
                        source
                    )
                    obj_id, created = save_record(
                        *args,
                        amount=amount,
                        blockheightid=None,
                        index=output.index,
                        inputs=inputs_data,
                        tx_timestamp=now
                    )
                    has_updated_output = has_updated_output or created

                    if created:
                        # Publish MQTT message
                        data = {
                            'txid': tx_hash,
                            'recipient': slp_address,
                            'amount': amount,
                            'token_type': 'slp',
                            'token_id': token_id
                        }
                        mqtt_client.publish(f"transactions/{slp_address}", json.dumps(data), qos=1)

                        client_acknowledgement(obj_id)
                    
                    if output.slp_token.is_mint_baton:
                        token_obj = Token.objects.filter(tokenid=token_id).first()
                        if token_obj:
                            token_obj.save_minting_baton_info({
                                "txid": tx_hash,
                                "index": output.index,
                                "address": slp_address,
                            })
                    msg = f"{source}: {tx_hash} | {slp_address} | {amount} | {token_id}"
                    LOGGER.info(msg)

            if has_subscribed_input and not has_updated_output:
                LOGGER.info(f"manually parsing wallet history of tx({tx_hash})")
                parse_tx_wallet_histories.delay(tx_hash)


class Command(BaseCommand):
    help = "Run the mempool tracker using BCHD GRPC stream"

    def handle(self, *args, **options):
        run()
