import logging
import requests
from functools import lru_cache

from stablehedge.apps import LOGGER

from main import models as main_models
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
    try:
        send_post_broadcast_notifications(transaction)
    except Exception as error:
        LOGGER.exception(error)
    return True, txid


def resolve_spending_txid(txid:str, vout:int):
    obj = main_models.Transaction.objects.filter(txid=txid, index=vout).first()
    if obj:
        return obj.spending_txid

    if NODE.BCH.rpc_connection.gettxout(txid, vout):
        return

    if BCH_NETWORK == "mainnet":
        return get_spending_txid_blockchair(txid, vout)
    else:
        return # chipnet version here


@lru_cache(maxsize=128)
def get_spending_txid_blockchair(txid:str, vout:int):
    """
        Gets spending txid from blockchair
        - only for mainnet
        - rate limited, see: https://blockchair.com/api/docs#link_M05
    """
    if not re.match("[0-9a-fA-F]{64}", txid):
        return

    vout = int(vout)
    if vout < 0:
        return

    url = f"https://api.blockchair.com/bitcoin-cash/dashboards/transaction/{txid}/"
    response = requests.get(url)
    response_data = response.json()
    try:
        tx_data = response_data["data"][txid]
        output_data = tx_data["outputs"][vout]
        spending_txid = output_data["spending_transaction_hash"]
        return spending_txid
    except (KeyError, TypeError) as exception:
        logging.exception(exception)
