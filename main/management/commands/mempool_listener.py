from django.core.management.base import BaseCommand
import paho.mqtt.client as mqtt
from django.conf import settings
import json
import time
import logging
from json.decoder import JSONDecodeError
from main.tasks import process_mempool_transaction_throttled


LOGGER = logging.getLogger(__name__)

mqtt_client_id = f"watchtower-{settings.BCH_NETWORK}-mempool"
if settings.BCH_NETWORK == 'mainnet':
    mqtt_client = mqtt.Client(transport='websockets', client_id=mqtt_client_id, clean_session=False)
    mqtt_client.tls_set()
else:
    mqtt_client = mqtt.Client(client_id=mqtt_client_id, clean_session=False)

mqtt_client.connect(settings.MQTT_HOST, settings.MQTT_PORT, 10)


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
            tx_hex = None
            if 'tx_hex' in payload.keys():
                tx_hex = payload['tx_hex']
            process_mempool_transaction_throttled.apply_async(
                (txid, tx_hex)
            )
    except JSONDecodeError:
        pass


FIRST_RECONNECT_DELAY = 1
RECONNECT_RATE = 2
MAX_RECONNECT_COUNT = 12
MAX_RECONNECT_DELAY = 60

def on_disconnect(client, userdata, rc):
    LOGGER.info(f"Disconnected with result code: {rc}")
    reconnect_count, reconnect_delay = 0, FIRST_RECONNECT_DELAY
    while reconnect_count < MAX_RECONNECT_COUNT:
        LOGGER.info(f"Reconnecting in {reconnect_delay} seconds...")
        time.sleep(reconnect_delay)

        try:
            client.reconnect()
            LOGGER.info("Reconnected successfully!")
            return
        except Exception as err:
            LOGGER.error(f"{err}. Reconnect failed. Retrying...")

        reconnect_delay *= RECONNECT_RATE
        reconnect_delay = min(reconnect_delay, MAX_RECONNECT_DELAY)
        reconnect_count += 1
    LOGGER.info(f"Reconnect failed after {reconnect_count} attempts. Exiting...")



# client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.on_disconnect = on_disconnect


# Blocking call that processes network traffic, dispatches callbacks and
# handles reconnecting.
# Other loop*() functions are available that give a threaded interface and a
# manual interface.
class Command(BaseCommand):
    help = 'Run the mempool listener'

    def handle(self, *args, **options):
        mqtt_client.loop_forever()
