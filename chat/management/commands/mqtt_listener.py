from django.core.management.base import BaseCommand
import paho.mqtt.client as mqtt
from django.utils import timezone
from django.conf import settings
import json
import logging
import time
from json.decoder import JSONDecodeError

from chat.models import Conversation, ChatIdentity
from main.models import Address
from chat.tasks import send_chat_notication


LOGGER = logging.getLogger(__name__)

# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    LOGGER.info("Connected to MQTT broker with result code " + str(rc))

    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe("chat/#")

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


mqtt_client_id = f"watchtower-{settings.BCH_NETWORK}-chat"
if settings.BCH_NETWORK == 'mainnet':
    client = mqtt.Client(transport='websockets', client_id=mqtt_client_id, clean_session=False)
    client.tls_set()
else:
    client = mqtt.Client(client_id=mqtt_client_id, clean_session=False)

client.on_connect = on_connect
client.on_disconnect = on_disconnect


client.connect(settings.MQTT_HOST, settings.MQTT_PORT, 10)

# Blocking call that processes network traffic, dispatches callbacks and
# handles reconnecting.
# Other loop*() functions are available that give a threaded interface and a
# manual interface.
class Command(BaseCommand):
    help = 'Run the MQTT listener'

    def handle(self, *args, **options):
        client.loop_forever()
