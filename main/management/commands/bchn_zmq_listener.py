#!/usr/bin/env python2
# Copyright (c) 2014-2016 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.


from django.core.management.base import BaseCommand
from django.conf import settings

from main.utils.queries.node import Node

from bitcash import transaction
import logging
import binascii
import zmq
import json
import paho.mqtt.client as mqtt


mqtt_client = mqtt.Client()
mqtt_client.connect("docker-host", 1883, 10)
mqtt_client.loop_start()


LOGGER = logging.getLogger(__name__)
node = Node()

class ZMQHandler():

    def __init__(self):
        self.url = f"tcp://{settings.BCHN_HOST}:28332"

        self.zmqContext = zmq.Context()
        self.zmqSubSocket = self.zmqContext.socket(zmq.SUB)
        self.zmqSubSocket.setsockopt_string(zmq.SUBSCRIBE, "rawtx")
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
                    msg = mqtt_client.publish('mempool', json.dumps(data), qos=2)
                    LOGGER.info('New mempool tx pushed to MQTT: ' + txid)

        except KeyboardInterrupt:
            self.zmqContext.destroy()

class Command(BaseCommand):
    help = "Start mempool tracker using ZMQ"

    def handle(self, *args, **options):
        daemon = ZMQHandler()
        daemon.start()
