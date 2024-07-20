import json
import paho.mqtt.client as mqtt
import paho.mqtt.publish as mqtt_publish

from django.conf import settings


def connect_to_mqtt(client_id=None):
    if not client_id:
        client_id = f"watchtower-{settings.BCH_NETWORK}-transactions-publisher"
    if settings.BCH_NETWORK == 'mainnet':
        mqtt_client = mqtt.Client(client_id=client_id, transport='websockets')
        mqtt_client.tls_set()
    else:
        mqtt_client = mqtt.Client(client_id=client_id, clean_session=True)
    mqtt_client.connect(settings.MQTT_HOST, settings.MQTT_PORT, 10)
    return mqtt_client


def publish_message(topic, message, qos=0):
    kwargs = dict(
        qos=qos,
        hostname=settings.MQTT_HOST,
        port=settings.MQTT_PORT,
        keepalive=10,
    )

    if settings.BCH_NETWORK == 'mainnet':
        kwargs["transport"] = "websockets"
        kwargs["tls"] = {}

    if isinstance(message, (dict, list)):
        message = json.dumps(message)

    return mqtt_publish.single(topic, message, **kwargs)
