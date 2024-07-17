import json

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from main.mqtt import connect_to_mqtt
from main.utils.queries.node import Node


NODE = Node()

def send_post_broadcast_notifications(transaction, extra_data:dict=None):
    results = []
    mqtt_client = connect_to_mqtt()
    mqtt_client.loop_start()

    if extra_data:
        try:
            json.dumps(extra_data)
        except:
            extra_data = None

    if not isinstance(extra_data, dict):
        extra_data = {}

    tx = NODE.BCH._decode_raw_transaction(transaction)

    input_0 = tx['vin'][0]
    input_details = NODE.BCH.get_input_details(input_0['txid'], input_0['vout'])
    sender_0 = input_details['address']

    for tx_out in tx['vout']:
        _addrs = tx_out.get('scriptPubKey').get('addresses')
        if _addrs:
            address = _addrs[0]

            # Send mqtt notif
            data = {
                'token': 'bch',
                'txid': tx['txid'],
                'recipient': address,
                'sender_0': sender_0,
                'decimals': 8,
                'value': round(tx_out['value'] * (10 ** 8)),
                **extra_data
            }
            mqtt_client.publish(f"transactions/{address}", json.dumps(data), qos=1)

            # Send websocket notif
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "bch", 
                {
                    "type": "send_update",
                    "data": data
                }
            )

            results.append(data)

    mqtt_client.loop_stop()
    return results