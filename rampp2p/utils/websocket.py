from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import decimal
import datetime

import logging
logger = logging.getLogger(__name__)

def serialize_data(data):
    if isinstance(data, dict):
        return {k: serialize_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [serialize_data(v) for v in data]
    elif isinstance(data, decimal.Decimal):
        return str(data)  # or float(data) if you prefer
    elif isinstance(data, datetime.datetime):
        return str(data)
    else:
        return data
    
def send_message(data, room_name):
    channel_layer = get_channel_layer()
    serialized_data = serialize_data(data)
    async_to_sync(channel_layer.group_send)(
        room_name,
        {
            "type": "send_message",
            "message": serialized_data,
        }
    )

def send_order_update(data, order_id):
    room_name = f'ramp-p2p-subscribe-order-{order_id}'
    send_message(data, room_name)

def send_market_price(data, currency):
    room_name = f'ramp-p2p-subscribe-market-price-{currency}'
    send_message(data, room_name)

def send_general_update(data, wallet_hash):
    room_name = f'ramp-p2p-subscribe-general-{wallet_hash}'
    send_message(data, room_name)

def send_cashin_order_alert(data, wallet_hash):
    room_name = f'ramp-p2p-subscribe-cashin-alerts-{wallet_hash}'
    send_message(data, room_name)