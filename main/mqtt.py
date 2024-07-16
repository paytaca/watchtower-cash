import json
import paho.mqtt.client as mqtt
import paho.mqtt.publish as mqtt_publish

from django.conf import settings


def connect_to_mqtt():
    if settings.BCH_NETWORK == 'mainnet':
        mqtt_client = mqtt.Client(transport='websockets')
        mqtt_client.tls_set()
    else:
        mqtt_client = mqtt.Client()
    mqtt_client.connect(settings.MQTT_HOST, settings.MQTT_PORT, 10)
    # mqtt_client.loop_start()
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
