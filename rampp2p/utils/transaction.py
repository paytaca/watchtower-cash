from rampp2p.tasks.transaction_tasks import execute_subprocess, handle_transaction
from main.utils.queries.node import Node

import logging
logger = logging.getLogger(__name__)

def validate_transaction(txid: str, **kwargs):
    '''
    Validates if a given transaction satisfies the prerequisites of its contract.
    Executes a subprocess to fetch raw transaction data, sends this data to `verify_tx_out` for
    validation, then updates the order's status if valid.
    '''
    logger.warning(f'Validating tx: {txid}')

    # result = {}

    # try:
    #     node = Node()
    #     txn = node.BCH.get_transaction(txid)
    #     result['valid'] = True
    #     result['details'] = txn
    # except Exception as err:
    #     result['valid'] = False
    #     result['error'] = err.args[0]
    #     result['details'] = None

    # logger.warning(f'txn:{txn}')

    # handle_transaction.s(
    #     kwargs.get('action'),
    #     kwargs.get('contract_id'),
    #     txn
    # )

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