from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

# Websocket messages
# Message pattern:
# {
#     "resource": "resource-name",
#     "action": "type-of-update",
#     "meta": { "arbitrary-data": "preferably-as-an-object" },
# }


def send_long_account_update(wallet_hash:str, action:str=""):
    room_name = f"updates_{wallet_hash}"
    data = { "resource": "long_account", "action": action }

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        room_name, 
        { "type": "send_update", "data": data }
    )


def send_offer_settlement_update(hedge_position_offer_obj):
    hedge_position_obj = hedge_position_offer_obj.hedge_position 
    if not hedge_position_obj:
        return

    channel_layer = get_channel_layer()
    data = {
        "resource": "hedge_position_offer",
        "action": "settlement",
        "meta": { "address": hedge_position_obj.address }
    }
    if hedge_position_obj.hedge_wallet_hash:
        room_name = f"updates_{hedge_position_obj.hedge_wallet_hash}"
        data["meta"]["position"] = "hedge"
        async_to_sync(channel_layer.group_send)(
            room_name, 
            { "type": "send_update", "data": data }
        )

    if hedge_position_obj.long_wallet_hash:
        room_name = f"updates_{hedge_position_obj.long_wallet_hash}"
        data["meta"]["position"] = "long"
        async_to_sync(channel_layer.group_send)(
            room_name, 
            { "type": "send_update", "data": data }
        )


def send_hedge_position_offer_update(hedge_position_offer_obj, action:str="", metadata=None):
    room_names = []
    if hedge_position_offer_obj.wallet_hash:
        room_names.append(f"updates_{hedge_position_offer_obj.wallet_hash}")

    if hedge_position_offer_obj.get_counter_party_info():
        counter_party_wallet_hash = hedge_position_offer_obj.get_counter_party_info().wallet_hash
        room_names.append(f"updates_{counter_party_wallet_hash}")

    if not len(room_names):
        return

    channel_layer = get_channel_layer()
    data = {
        "resource": "hedge_position_offer",
        "action": action,
        "meta": {
            "id": hedge_position_offer_obj.id,
            "position": hedge_position_offer_obj.position,
        }
    }

    if isinstance(metadata, dict):
        data["meta"].update(metadata)

    for room_name in room_names:
        async_to_sync(channel_layer.group_send)(
            room_name, 
            { "type": "send_update", "data": data }
        )


def send_funding_tx_update(hedge_position_obj, position:str="", tx_hash:str=""):
    channel_layer = get_channel_layer()
    data = {
        "resource": "hedge_position",
        "action": "funding_proposal",
        "meta": { "address": hedge_position_obj.address }
    }

    if position:
        data["meta"]["updated_position"] = position

    if tx_hash:
        data["meta"]["new_tx_hash"] = tx_hash

    if hedge_position_obj.hedge_wallet_hash:
        room_name = f"updates_{hedge_position_obj.hedge_wallet_hash}"
        data["meta"]["position"] = "hedge"
        async_to_sync(channel_layer.group_send)(
            room_name, 
            { "type": "send_update", "data": data }
        )

    if hedge_position_obj.long_wallet_hash:
        room_name = f"updates_{hedge_position_obj.long_wallet_hash}"
        data["meta"]["position"] = "long"
        async_to_sync(channel_layer.group_send)(
            room_name, 
            { "type": "send_update", "data": data }
        )

def send_settlement_update(hedge_position_obj):
    channel_layer = get_channel_layer()
    data = {
        "resource": "hedge_position",
        "action": "settlement",
        "meta": { "address": hedge_position_obj.address }
    }

    if hedge_position_obj.hedge_wallet_hash:
        room_name = f"updates_{hedge_position_obj.hedge_wallet_hash}"
        data["meta"]["position"] = "hedge"
        async_to_sync(channel_layer.group_send)(
            room_name, 
            { "type": "send_update", "data": data }
        )

    if hedge_position_obj.long_wallet_hash:
        room_name = f"updates_{hedge_position_obj.long_wallet_hash}"
        data["meta"]["position"] = "long"
        async_to_sync(channel_layer.group_send)(
            room_name, 
            { "type": "send_update", "data": data }
        )

def send_mutual_redemption_update(mutual_redemption_obj, action=""):
    channel_layer = get_channel_layer()
    hedge_position_obj = mutual_redemption_obj.hedge_position
    data = {
        "resource": "mutual_redemption",
        "action": action,
        "meta": {
            "id": mutual_redemption_obj.id,
            "redemption_type": mutual_redemption_obj.redemption_type,
            "address": hedge_position_obj.address,
        }
    }

    if hedge_position_obj.hedge_wallet_hash:
        room_name = f"updates_{hedge_position_obj.hedge_wallet_hash}"
        data["meta"]["position"] = "hedge"
        async_to_sync(channel_layer.group_send)(
            room_name, 
            { "type": "send_update", "data": data }
        )

    if hedge_position_obj.long_wallet_hash:
        room_name = f"updates_{hedge_position_obj.long_wallet_hash}"
        data["meta"]["position"] = "long"
        async_to_sync(channel_layer.group_send)(
            room_name, 
            { "type": "send_update", "data": data }
        )
