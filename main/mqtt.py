import json
import paho.mqtt.client as mqtt
import paho.mqtt.publish as mqtt_publish
from django.conf import settings


# def connect_to_mqtt(client_id=None):
#     if not client_id:
#         client_id = f"watchtower-{settings.BCH_NETWORK}-transactions-publisher"
#     if settings.BCH_NETWORK == 'mainnet':
#         mqtt_client = mqtt.Client(client_id=client_id, transport='websockets')
#         mqtt_client.tls_set()
#     else:
#         mqtt_client = mqtt.Client(client_id=client_id, clean_session=False)
#     mqtt_client.connect(settings.MQTT_HOST, settings.MQTT_PORT, 10)
#     return mqtt_client


def publish_message(topic, message, qos=1, message_type='transactions'):
    client_id = f"watchtower-{settings.BCH_NETWORK}-{message_type}-publisher"
    kwargs = dict(
        client_id=client_id,
        qos=qos,
        hostname=settings.MQTT_HOST,
        port=settings.MQTT_PORT,
        keepalive=10,
        retain=True
    )

    if settings.BCH_NETWORK == 'mainnet':
        kwargs["transport"] = "websockets"
        kwargs["tls"] = {}

    message = json.dumps(message, default=str)
    return mqtt_publish.single(topic, message, **kwargs)
