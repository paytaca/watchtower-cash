#!/usr/bin/env python2
# Copyright (c) 2014-2016 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.


from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings

from main.utils.queries.bchn import *
from main.models import (
    Transaction,
    Subscription,
)
from main.tasks import (
    save_record,
    client_acknowledgement,
    send_telegram_message,
    parse_tx_wallet_histories,
    process_cashtoken_tx,
)

import logging
import binascii
import zmq
import requests


LOGGER = logging.getLogger(__name__)


class ZMQHandler():

    def __init__(self):
        self.url = "tcp://zmq:28332"
        self.BCHN = BCHN()

        self.zmqContext = zmq.Context()
        self.zmqSubSocket = self.zmqContext.socket(zmq.SUB)
        self.zmqSubSocket.setsockopt_string(zmq.SUBSCRIBE, "hashtx")
        self.zmqSubSocket.connect(self.url)

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

                    for _input in inputs:
                        txid = _input['txid']
                        amount = _input['value']
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
                                    "amount": amount,
                                    "outpoint_txid": txid,
                                    "outpoint_index": index,
                                })
                    
                    for output in outputs:
                        scriptPubKey = output['scriptPubKey']

                        if 'addresses' in scriptPubKey.keys():
                            bchaddress = scriptPubKey['addresses'][0]
                            amount = output['value']
                            source = self.BCHN.source
                            index = output['n']

                            if 'tokenData' in output.keys():
                                process_cashtoken_tx(
                                    output['tokenData'],
                                    output['scriptPubKey']['addresses'][0],
                                    tx_hash,
                                    index=index,
                                    value=(output['value'] * (10 ** 8))
                                )
                            else:
                                args = (
                                    'bch',
                                    bchaddress,
                                    tx_hash,
                                    amount,
                                    source,
                                    None,
                                    index
                                )
                                now = timezone.now().timestamp()
                                obj_id, created = save_record(*args, inputs=inputs_data, tx_timestamp=now)
                                has_updated_output = has_updated_output or created
                                if created:
                                    third_parties = client_acknowledgement(obj_id)
                                    for platform in third_parties:
                                        if 'telegram' in platform:
                                            message = platform[1]
                                            chat_id = platform[2]
                                            send_telegram_message(message, chat_id)
                                msg = f"{source}: {tx_hash} | {bchaddress} | {amount} "
                                LOGGER.info(msg)
                    
                    if has_subscribed_input and not has_updated_output:
                        LOGGER.info(f"manually parsing wallet history of tx({tx_hash})")
                        parse_tx_wallet_histories.delay(tx_hash)

        except KeyboardInterrupt:
            zmqContext.destroy()

class Command(BaseCommand):
    help = "Start mempool tracker using ZMQ"

    def handle(self, *args, **options):
        daemon = ZMQHandler()
        daemon.start()
