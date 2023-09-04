from django.conf import settings

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


def send_websocket_data(
    room_id,
    operation,
    json_data,
    room_name=settings.VOUCHER_ROOM
):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"{room_name}_{room_id}",
        {
            "type": "send_data",
            "operation": operation,
            "data": json_data
        }
    )
