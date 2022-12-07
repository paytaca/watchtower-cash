from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

def send_device_update(pos_device_obj, action:str="", update_data=None):
    channel_layer = get_channel_layer()
    room_names = [
        f"paytacapos-{pos_device_obj.wallet_hash}",
        f"paytacapos-{pos_device_obj.wallet_hash}-{pos_device_obj.posid}",
    ]

    data = {
        "resource": "pos_device",
        "action": action,
        "object": { "wallet_hash": pos_device_obj.wallet_hash, "posid": pos_device_obj.posid }
    }
    if update_data:
        data["data"] = update_data

    for room_name in room_names:
        async_to_sync(channel_layer.group_send)(
            room_name, 
            { "type": "send_update", "data": data }
        )
