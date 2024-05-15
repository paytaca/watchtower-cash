import paho.mqtt.client as mqtt
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
