from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

def notify_subprocess_completion(result, **kwargs):
    wallet_hash = kwargs.get('wallet_hash')
    room_name = f'ramp-p2p-updates-{wallet_hash}'
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        room_name,
        {
            'type': 'notify',
            'message': result
        }
    )