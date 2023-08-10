#!/usr/bin/env python2
# Copyright (c) 2014-2016 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.


from django.core.management.base import BaseCommand
from django.conf import settings

from main.utils.queries.bchn import BCHN

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
        self.url = f"tcp://{settings.BCHN_HOST}:28332"
        self.BCHN = BCHN()

        self.zmqContext = zmq.Context()
        self.zmqSubSocket = self.zmqContext.socket(zmq.SUB)
        self.zmqSubSocket.setsockopt_string(zmq.SUBSCRIBE, "hashtx")
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

                if topic == "hashtx":
                    tx_hash = binascii.hexlify(body).decode()
                    data = {
                        'txid': tx_hash
                    }
                    msg = mqtt_client.publish('mempool', json.dumps(data), qos=1)
                    LOGGER.info('New mempool tx pushed to MQTT: ' + tx_hash)

        except KeyboardInterrupt:
            self.zmqContext.destroy()

class Command(BaseCommand):
    help = "Start mempool tracker using ZMQ"

    def handle(self, *args, **options):
        daemon = ZMQHandler()
        daemon.start()
