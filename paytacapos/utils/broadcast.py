from main.tasks import broadcast_transaction as broadcast_tx

def broadcast_transaction(tx_hex):
    response = { "success": False }

    success, result = broadcast_tx(tx_hex)
    if "already have transaction" in result:
        success = True
    if success:
        response["txid"] = result.split(" ")[-1]
        response["success"] = True
        return response
    else:
        response["error"] = result
        response["success"] = False
        return response
