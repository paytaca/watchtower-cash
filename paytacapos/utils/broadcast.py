from main.tasks import broadcast_transaction as broadcast_tx
from main.utils.broadcast import send_post_broadcast_notifications

def broadcast_transaction(tx_hex):
    response = { "success": False }

    success, result = broadcast_tx(tx_hex)
    if "already have transaction" in result:
        success = True
    if success:
        send_post_broadcast_notifications(tx_hex)
        response["txid"] = result.split(" ")[-1]
        response["success"] = True
        return response
    else:
        response["error"] = result
        response["success"] = False
        return response
