#!/usr/bin/env python
# Copyright (c) 2014-2016 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.


from django.core.management.base import BaseCommand
from django.conf import settings
from main.mqtt import publish_message
from bitcash import transaction
import logging
import binascii
import zmq


LOGGER = logging.getLogger(__name__)

class ZMQHandler():

    def __init__(self):
        self.url = f"tcp://{settings.BCHN_HOST}:28332"

        self.zmqContext = zmq.Context()
        self.zmqSubSocket = self.zmqContext.socket(zmq.SUB)
        self.zmqSubSocket.setsockopt_string(zmq.SUBSCRIBE, "rawtx")
        self.zmqSubSocket.setsockopt_string(zmq.SUBSCRIBE, "hashds")
        self.zmqSubSocket.setsockopt(zmq.TCP_KEEPALIVE,1)
        self.zmqSubSocket.setsockopt(zmq.TCP_KEEPALIVE_CNT,10)
        self.zmqSubSocket.setsockopt(zmq.TCP_KEEPALIVE_IDLE,1)
        self.zmqSubSocket.setsockopt(zmq.TCP_KEEPALIVE_INTVL,1)
        self.zmqSubSocket.connect(self.url)

    def start(self):
        try:
            while True:
                msg = self.zmqSubSocket.recv_multipart()
                topic = msg[0].decode()
                body = msg[1]

                if topic == "rawtx":
                    tx_hex = binascii.hexlify(body).decode()
                    txid = transaction.calc_txid(tx_hex)
                    data = {
                        'txid': txid,
                        'tx_hex': tx_hex
                    }
                    publish_message('mempool', data, qos=1, message_type='mempool')
                    LOGGER.info('New mempool tx pushed to MQTT: ' + txid)

                if topic == "hashds":
                    hash_ds = binascii.hexlify(body).decode()
                    LOGGER.info('New double spend detected: ' + str(hash_ds))

        except KeyboardInterrupt:
            self.zmqContext.destroy()

class Command(BaseCommand):
    help = "Start mempool tracker using ZMQ"

    def handle(self, *args, **options):
        daemon = ZMQHandler()
        daemon.start()
