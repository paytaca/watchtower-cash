# Ideally put all files/code pulled from outside the app(anyhedge) in here
# careful removing unused imports here
import bitcoin
from main.models import Transaction
from main.utils.queries.bchn import BCHN
from main.utils.queries.bchd import BCHDQuery
from main.utils.broadcast import send_post_broadcast_notifications
from main.models import TransactionMetaAttribute
from main.tasks import parse_tx_wallet_histories

from notifications.utils.send import send_push_notification_to_wallet_hashes, NotificationTypes


def get_bchn_instance():
    return BCHN()


def broadcast_transaction(tx_hex):
    response = { "success": False }
    txid = bitcoin.txhash(tx_hex)
    if Transaction.objects.filter(txid=txid).exists():
        success = True
    else:
        bchn = BCHN()
        result = bchn.broadcast_transaction(tx_hex)
        success = bool(result)

    if "already have transaction" in result:
        success = True
    if success:
        send_post_broadcast_notifications
        response["txid"] = txid
        response["success"] = True
        return response
    else:
        response["error"] = result
        response["success"] = False
        return response
