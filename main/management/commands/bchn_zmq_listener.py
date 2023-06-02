#!/usr/bin/env python2
# Copyright (c) 2014-2016 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.


from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings

from main.utils.queries.bitcoin_verde import *
from main.utils.queries.bchn import *
from main.models import (
    Transaction,
    Subscription,
)
from main.tasks import (
    save_record,
    client_acknowledgement,
    parse_tx_wallet_histories,
    process_cashtoken_tx,
)

import logging
import binascii
import zmq
import paho.mqtt.client as mqtt


mqtt_client = mqtt.Client()
mqtt_client.connect("docker-host", 1883, 10)
mqtt_client.loop_start()


LOGGER = logging.getLogger(__name__)


class ZMQHandler():

    def __init__(self):
        self.url = "tcp://zmq:28332"
        self.BCHN = BCHN()

        self.zmqContext = zmq.Context()
        self.zmqSubSocket = self.zmqContext.socket(zmq.SUB)
        self.zmqSubSocket.setsockopt_string(zmq.SUBSCRIBE, "hashtx")
        self.zmqSubSocket.connect(self.url)
    
    def has_op_ret(self, first_txn_output):
        scriptPubKey = first_txn_output['scriptPubKey']
        asm = scriptPubKey['asm']
        out_type = scriptPubKey['type']

        main_op_code = asm.split(' ')[0].upper()
        is_op_ret = main_op_code == 'OP_RETURN'
        is_null_data = out_type == 'nulldata'

        return is_op_ret and is_null_data

    def start(self):
        try:
            while True:
                msg = self.zmqSubSocket.recv_multipart()
                topic = msg[0].decode()
                body = msg[1]

                if topic == "hashtx":
                    tx_hash = binascii.hexlify(body).decode()
                    tx = self.BCHN._get_raw_transaction(tx_hash)
                    inputs = tx['vin']
                    outputs = tx['vout']

                    if 'coinbase' in inputs[0].keys():
                        return

                    has_subscribed_input = False
                    has_updated_output = False
                    inputs_data = []


                    # check op returns to parse SLP transactions using Bitcoin Verde

                    if self.has_op_ret(outputs[0]) and settings.BCH_NETWORK == 'mainnet':
                        bcv = BitcoinVerde()
                        is_valid_slp_txn = bcv.validate_transaction(tx_hash)
                        
                        if is_valid_slp_txn:
                            txn = bcv.get_transaction(tx_hash)

                            for _input in txn['inputs']:
                                address = _input['address']
                                subscription = Subscription.objects.filter(
                                    address__address=address
                                )
                                if subscription.exists():
                                    inputs_data.append({
                                        'token': txn['token_id'],
                                        'address': address,
                                        'amount': _input['amount'],
                                        'value': _input['value'],
                                        'outpoint_index': _input['spent_index'],
                                        'outpoint_txid': _input['txid']
                                    })

                            for output in txn['outputs']:
                                obj_id, created = save_record(
                                    output['token_id'],
                                    output['address'],
                                    tx_hash,
                                    bcv.source,
                                    inputs=inputs_data,
                                    value=output['value'],
                                    amount=output['amount'],
                                    index=output['index'],
                                    tx_timestamp=txn['timestamp']
                                )

                                if created:
                                    client_acknowledgement(obj_id)


                    for _input in inputs:
                        txid = _input['txid']
                        value = int(_input['value'] * (10 ** 8))
                        index = _input['vout']

                        ancestor_tx = self.BCHN._get_raw_transaction(txid)
                        ancestor_spubkey = ancestor_tx['vout'][index]['scriptPubKey']

                        if 'addresses' in ancestor_spubkey.keys():
                            address = ancestor_spubkey['addresses'][0]
                            spent_transactions = Transaction.objects.filter(txid=txid, index=index)
                            spent_transactions.update(spent=True, spending_txid=tx_hash)
                            has_existing_wallet = spent_transactions.filter(wallet__isnull=False).exists()
                            has_subscribed_input = has_subscribed_input or has_existing_wallet

                            subscription = Subscription.objects.filter(
                                address__address=address
                            )
                            if subscription.exists():
                                inputs_data.append({
                                    "token": "bch",
                                    "address": address,
                                    "amount": None,
                                    "value": value,
                                    "outpoint_txid": txid,
                                    "outpoint_index": index,
                                })
                    
                    for output in outputs:
                        scriptPubKey = output['scriptPubKey']

                        if 'addresses' in scriptPubKey.keys():
                            bchaddress = scriptPubKey['addresses'][0]
                            value = int(output['value'] * (10 ** 8))
                            source = self.BCHN.source
                            index = output['n']

                            token_id = 'bch'
                            amount = ''
                            decimals = None
                            created = False
                            if 'tokenData' in output.keys():
                                saved_token_data = process_cashtoken_tx(
                                    output['tokenData'],
                                    output['scriptPubKey']['addresses'][0],
                                    tx_hash,
                                    index=index,
                                    value=value
                                )
                                token_id = saved_token_data['token_id']
                                decimals = saved_token_data['decimals']
                                amount = str(saved_token_data['amount'])
                                created = saved_token_data['created']
                            else:
                                args = (
                                    token_id,
                                    bchaddress,
                                    tx_hash,
                                    source
                                )
                                now = timezone.now().timestamp()
                                obj_id, created = save_record(
                                    *args,
                                    value=value,
                                    blockheightid=None,
                                    index=index,
                                    inputs=inputs_data,
                                    tx_timestamp=now
                                )
                                has_updated_output = has_updated_output or created

                                txn_obj = Transaction.objects.get(id=obj_id)
                                decimals = txn_obj.get_token_decimals()
                                
                            if created:
                                # Publish MQTT message
                                data = {
                                    'txid': tx_hash,
                                    'recipient': bchaddress,
                                    'token': token_id,
                                    'decimals': decimals,
                                    'amount': amount,
                                    'value': value
                                }
                                LOGGER.info('Sending MQTT message: ' + str(data))
                                msg = mqtt_client.publish(f"transactions/{bchaddress}", json.dumps(data), qos=1)
                                LOGGER.info('MQTT message is published: ' + str(msg.is_published()))

                                client_acknowledgement(obj_id)

                                LOGGER.info(data)
                    
                    if has_subscribed_input and not has_updated_output:
                        LOGGER.info(f"manually parsing wallet history of tx({tx_hash})")
                        parse_tx_wallet_histories.delay(tx_hash)

        except KeyboardInterrupt:
            self.zmqContext.destroy()

class Command(BaseCommand):
    help = "Start mempool tracker using ZMQ"

    def handle(self, *args, **options):
        daemon = ZMQHandler()
        daemon.start()
