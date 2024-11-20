from main.tasks import NODE, process_mempool_transaction_fast
from main.utils.broadcast import send_post_broadcast_notifications


def get_locktime():
    return NODE.BCH.get_latest_block()


def test_transaction_accept(transaction):
    test_accept = NODE.BCH.test_mempool_accept(transaction)
    if not test_accept["allowed"]:
        return False, test_accept["reject-reason"]

    return True, test_accept["txid"]


def broadcast_transaction(transaction):
    valid_tx, error_or_txid = test_transaction_accept(transaction)
    if not valid_tx:
        return False, error_or_txid

    txid = error_or_txid
    txid = NODE.BCH.broadcast_transaction(transaction)
    process_mempool_transaction_fast(txid, transaction, True)
    send_post_broadcast_notifications(transaction)
    return True, txid
