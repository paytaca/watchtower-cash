import paho.mqtt.client as mqtt
import json
import logging
from json.decoder import JSONDecodeError

from chat.models import Conversation
from main.models import Address

LOGGER = logging.getLogger(__name__)

# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    LOGGER.info("Connected to MQTT broker with result code " + str(rc))

    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe("chat/#")

# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload)
        if 'from' in payload.keys() and 'to' in payload.keys():
            LOGGER.info(f"Chat messsage received from {payload['from']} to {payload['to']}!")
            try:
                conversation, _ = Conversation.objects.get_or_create(
                    from_address=Address.objects.get(address=payload['from']),
                    to_address=Address.objects.get(address=payload['to']),
                    topic=msg.topic
                )
                LOGGER.info('Conversation saved: ' + str(conversation.id))
            except Address.DoesNotExist:
                pass
    except JSONDecodeError:
        pass

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

client.connect("docker-host", 1883, 60)

# Blocking call that processes network traffic, dispatches callbacks and
# handles reconnecting.
# Other loop*() functions are available that give a threaded interface and a
# manual interface.
client.loop_forever()
