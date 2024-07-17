import bitcoin
from main.tasks import NODE
from main.models import Transaction
from main.utils.broadcast import send_post_broadcast_notifications

def broadcast_transaction(tx_hex):
    response = { "success": False }

    txid = bitcoin.txhash(tx_hex)
    if Transaction.objects.filter(txid=txid).exists():
        success = True
    else:
        result = NODE.BCH.broadcast_transaction(tx_hex)
        success = bool(result)

    if "already have transaction" in result:
        success = True
    if success:
        send_post_broadcast_notifications(tx_hex)
        response["txid"] = txid
        response["success"] = True
        return response
    else:
        response["error"] = result
        response["success"] = False
        return response
