# Ideally put all files/code pulled from outside the app(anyhedge) in here
# careful removing unused imports here
import logging

import bitcoin
from main.models import Transaction
from main.utils.queries.bchn import BCHN
from main.utils.queries.bchd import BCHDQuery
from main.utils.broadcast import broadcast_transaction_sync
from main.models import TransactionMetaAttribute
from main.tasks import (
    parse_tx_wallet_histories,
    process_mempool_transaction_fast,
    send_post_broadcast_notifications_task,
)

from notifications.utils.send import send_push_notification_to_wallet_hashes, NotificationTypes


LOGGER = logging.getLogger(__name__)


def get_bchn_instance():
    return BCHN()


def broadcast_transaction(tx_hex):
    response = { "success": False }
    txid = bitcoin.txhash(tx_hex)
    if Transaction.objects.filter(txid=txid).exists():
        response["txid"] = txid
        response["success"] = True
        return response

    result = broadcast_transaction_sync(tx_hex)
    if not result["success"]:
        response["error"] = result.get("error")
        return response

    txid = result["txid"]

    # The shared broadcast helper only records TransactionBroadcast and broadcasts
    # to the node. Trigger the same post-broadcast processing that the public
    # /broadcast/ endpoint does so the funding tx is indexed and notified about.
    try:
        process_mempool_transaction_fast.delay(txid, tx_hex, True)
    except Exception:
        LOGGER.exception(f"Failed to queue mempool processing for txid {txid}")

    try:
        send_post_broadcast_notifications_task.delay(tx_hex)
    except Exception:
        LOGGER.exception(f"Failed to queue post-broadcast notifications for txid {txid}")

    response["txid"] = txid
    response["success"] = True
    return response
