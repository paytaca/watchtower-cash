import json
import logging
import socket
import paho.mqtt.client as mqtt
import paho.mqtt.publish as mqtt_publish
from django.conf import settings

LOGGER = logging.getLogger(__name__)


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


def publish_message(topic, message, qos=1, message_type='transactions', timeout=5):
    """Publish MQTT message with timeout handling to prevent blocking.
    
    Args:
        topic: MQTT topic to publish to
        message: Message payload (will be JSON-encoded)
        qos: Quality of service level (default: 1)
        message_type: Type of message for client ID generation (default: 'transactions')
        timeout: Connection timeout in seconds (default: 5)
    
    Returns:
        Result of mqtt_publish.single() or None if timeout/error occurs
    """
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
    
    try:
        # Set socket timeout to prevent indefinite blocking
        original_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(timeout)
        try:
            return mqtt_publish.single(topic, message, **kwargs)
        finally:
            # Restore original timeout
            socket.setdefaulttimeout(original_timeout)
    except socket.timeout:
        LOGGER.warning(f"MQTT publish timeout after {timeout}s for topic: {topic}")
        return None
    except Exception as exc:
        LOGGER.error(f"MQTT publish error for topic {topic}: {exc}", exc_info=True)
        return None
