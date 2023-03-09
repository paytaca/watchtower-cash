#!/usr/bin/env python3
# Copyright (c) 2014-2021 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

from django.core.management.base import BaseCommand

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
)

import asyncio
import zmq
import zmq.asyncio
import signal
import struct
import sys
import logging

LOGGER = logging.getLogger(__name__)

if (sys.version_info.major, sys.version_info.minor) < (3, 5):
    print("This example only works with Python 3.5 and greater")
    sys.exit(1)


class ZMQHandler():
    def __init__(self):
        port = 28332
        tcp_url = f"tcp://127.0.0.1:{port}"

        self.loop = asyncio.get_event_loop()
        self.zmqContext = zmq.asyncio.Context()

        self.zmqSubSocket = self.zmqContext.socket(zmq.SUB)
        self.zmqSubSocket.setsockopt(zmq.RCVHWM, 0)
        self.zmqSubSocket.setsockopt_string(zmq.SUBSCRIBE, "hashblock")
        self.zmqSubSocket.setsockopt_string(zmq.SUBSCRIBE, "hashtx")
        self.zmqSubSocket.setsockopt_string(zmq.SUBSCRIBE, "rawblock")
        self.zmqSubSocket.setsockopt_string(zmq.SUBSCRIBE, "rawtx")
        self.zmqSubSocket.setsockopt_string(zmq.SUBSCRIBE, "sequence")
        self.zmqSubSocket.connect(tcp_url)

        LOGGER.info(f'Connected to ZMQ ({tcp_url})')
        self.BCHN = BCHN()

    async def handle(self) :
        topic, body, seq = await self.zmqSubSocket.recv_multipart()
        sequence = "Unknown"

        if len(seq) == 4:
            sequence = str(struct.unpack('<I', seq)[-1])
        seq_str = '(' + sequence + ') -'

        if topic == b"hashblock":
            pass
            # print('- HASH BLOCK ' + seq_str)
            # print(body.hex())
            
        elif topic == b"hashtx":
            LOGGER.info('- HASH TX  ' + seq_str)

            tx_hash = body.hex()
            tx = self.BCHN._get_raw_transaction(tx_hash)
            inputs = tx['vin']
            outputs = tx['vout']

            if 'coinbase' in inputs[0].keys():
                return

            for _input in inputs:
                txid = _input['txid']
                amount = _input['value']
                vout = _input['vout']

                ancestor_tx = self.BCHN._get_raw_transaction(txid)
                ancestor_spubkey = ancestor_tx['vout'][vout]['scriptPubKey']

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
                            # "index": index,
                            "token": "bch",
                            "address": address,
                            "amount": amount,
                            "outpoint_txid": txid,
                            "outpoint_index": len(outputs) - 1,
                        })
            
            for output in outputs:
                scriptPubKey = output['scriptPubKey']

                if 'addresses' in scriptPubKey.keys():
                    bchaddress = scriptPubKey['addresses'][0]
                    amount = output['value']

                    args = (
                        'bch',
                        bchaddress,
                        tx_hash,
                        amount,
                        source,
                        None,
                        output['n']
                    )
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
                parse_tx_wallet_histories.delay(tx_hash, is_bchd=False)

        elif topic == b"rawblock":
            pass
            # print('- RAW BLOCK HEADER ' + seq_str)
            # print(body[:80].hex())

        elif topic == b"rawtx":
            pass
            # print('- RAW TX ' + seq_str)
            # print(body.hex())

        elif topic == b"sequence":
            pass
            # hash = body[:32].hex()
            # label = chr(body[32])
            # mempool_sequence = None if len(body) != 32+1+8 else struct.unpack("<Q", body[32+1:])[0]
            # print('- SEQUENCE ' + seq_str)
            # print(hash, label, mempool_sequence)

        # schedule ourselves to receive the next message
        asyncio.ensure_future(self.handle())

    def start(self):
        self.loop.add_signal_handler(signal.SIGINT, self.stop)
        self.loop.create_task(self.handle())
        self.loop.run_forever()

    def stop(self):
        self.loop.stop()
        self.zmqContext.destroy()


class Command(BaseCommand):
    help = "Start mempool tracker using ZMQ"

    def handle(self, *args, **options):
        daemon = ZMQHandler()
        daemon.start()
