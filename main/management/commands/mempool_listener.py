from django.core.management.base import BaseCommand
from main.utils.queries.bchn import BCHN
import paho.mqtt.client as mqtt
from django.utils import timezone
import json
import logging
from json.decoder import JSONDecodeError

from main.utils import mempool


LOGGER = logging.getLogger(__name__)


bchn_client = BCHN()

mqtt_client = mqtt.Client()
mqtt_client.connect("docker-host", 1883, 10)


# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    LOGGER.info("Connected to MQTT broker with result code " + str(rc))

    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe("mempool")


# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload)
        if 'txid' in payload.keys():
            txid = payload['txid']
            mempool.process_tx(txid, bchn_client, mqtt_client)
    except JSONDecodeError:
        pass


# client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message


# Blocking call that processes network traffic, dispatches callbacks and
# handles reconnecting.
# Other loop*() functions are available that give a threaded interface and a
# manual interface.
class Command(BaseCommand):
    help = 'Run the mempool listener'

    def handle(self, *args, **options):
        mqtt_client.loop_forever()
