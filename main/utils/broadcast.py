import json
from hashlib import md5

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from main.mqtt import publish_message
from main.utils.queries.node import Node
from django.apps import apps

from main.models import Address


NODE = Node()

def send_post_broadcast_notifications(transaction, extra_data:dict=None):
    results = []
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
            device_id = []

            # get device ID from wallet hash of sender_0 address
            try:
                sender_wallet_hash = Address.objects.get(address=sender_0).wallet.wallet_hash
                device_wallet_model = apps.get_model("notifications", "DeviceWallet")
                device_wallet_check = device_wallet_model.objects.filter(wallet_hash=sender_wallet_hash)

                if device_wallet_check.exists():
                    for device in device_wallet_check.all():
                        gcm_device_id = device.gcm_device.device_id
                        apns_device_id = device.apns_device.device_id
                        gcm_device_id_hash = md5(str.encode(gcm_device_id)).hexdigest() if gcm_device_id else None
                        apns_device_id_hash = md5(str.encode(apns_device_id)).hexdigest() if apns_device_id else None
                        
                        if gcm_device_id_hash: device_id.append(gcm_device_id_hash)
                        if apns_device_id_hash: device_id.append(apns_device_id_hash)
                else:
                    device_id = []
            except:
                device_id = []

            # Send mqtt notif
            data = {
                'token': 'bch',
                'txid': tx['txid'],
                'recipient': address,
                'sender_0': sender_0,
                'decimals': 8,
                'value': round(tx_out['value'] * (10 ** 8)),
                'device_id': device_id,
                **extra_data
            }
            publish_message(f"transactions/{address}", data, qos=1)

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
    return results


def broadcast_to_engagementhub(data):
    publish_message('appnotifs', data, qos=0)
