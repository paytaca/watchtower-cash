import bitcoin
from main.tasks import NODE
from main.models import Transaction

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
        response["txid"] = txid
        response["success"] = True
        return response
    else:
        response["error"] = result
        response["success"] = False
        return response
