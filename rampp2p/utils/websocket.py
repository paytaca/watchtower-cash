from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

def send_order_update(data, order_id):
    room_name = f'ramp-p2p-updates-{order_id}'
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        room_name,
        {
            'type': 'notify',
            'data': data
        }
    )