from main.utils.broadcast import broadcast_transaction_sync, send_post_broadcast_notifications

def broadcast_transaction(tx_hex):
    response = { "success": False }

    broadcast_result = broadcast_transaction_sync(tx_hex)
    if broadcast_result['success']:
        send_post_broadcast_notifications(tx_hex)
        response["txid"] = broadcast_result['txid']
        response["success"] = True
        return response
    else:
        response["error"] = broadcast_result.get('error', 'broadcast failed')
        response["success"] = False
        return response
