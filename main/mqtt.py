import paho.mqtt.client as mqtt
from django.conf import settings


if settings.BCH_NETWORK == 'mainnet':
    client = mqtt.Client(transport='websockets')
    client.tls_set()
else:
    client = mqtt.Client()

client.connect(settings.MQTT_HOST, settings.MQTT_PORT, 10)
