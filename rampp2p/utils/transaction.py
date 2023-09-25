from rampp2p.tasks.transaction_tasks import execute_subprocess, handle_transaction
from django.conf import settings
from main.utils.queries.node import Node
import requests

import logging
logger = logging.getLogger(__name__)

def validate_transaction(txid: str, **kwargs):
    '''
    Validates if a given transaction satisfies the prerequisites of its contract.
    Executes a subprocess to fetch raw transaction data, sends this data to `verify_tx_out` for
    validation, then updates the order's status if valid.
    '''
    logger.warning(f'Validating tx: {txid}')

    if settings.BCH_NETWORK == 'chipnet':
        txn = get_txn_details(txid)
        handle_transaction.apply_async(
            args=(
                txn,
                kwargs.get('action'),
                kwargs.get('contract_id')
            )
        )
    else:
        path = './rampp2p/js/src/'
        command = 'node {}transaction.js {}'.format(
            path,
            txid
        )
        return execute_subprocess.apply_async(
                    (command,), 
                    link=handle_transaction.s(
                        kwargs.get('action'),
                        kwargs.get('contract_id')
                    )
                )

def get_txn_details(txid: str):
    try:
        url = f'https://chipnet.watchtower.cash/api/transactions/{txid}/' 
        response = requests.get(url)
        txn = response.json()
        return txn
    except Exception as err:
        logger.warning(f'err: {err.args[0]}')