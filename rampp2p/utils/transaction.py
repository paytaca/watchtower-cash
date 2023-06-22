from rampp2p.tasks.transaction_tasks import execute_subprocess, verify_tx_out, rates_handler

import logging
logger = logging.getLogger(__name__)

def validate_transaction(txid: str, **kwargs):
    '''
    Validates if a given transaction satisfies the prerequisites of its contract.
    Executes a subprocess to fetch raw transaction data, sends this data to `verify_tx_out` for
    validation, then updates the order's status if valid.
    '''
    logger.warning(f'Validating tx: {txid}')
    path = './rampp2p/escrow/src/'
    command = 'node {}transaction.js {}'.format(
        path,
        txid
    )
    return execute_subprocess.apply_async(
                (command,), 
                link=verify_tx_out.s(
                    txid=txid,
                    action=kwargs.get('action'),
                    contract_id=kwargs.get('contract_id'),
                )
            )

def get_rates(currency):
    '''
    Returns the current price of BCH in several different currencies.
    '''
    logger.warning('Retrieving the market price of BCH')
    path = './rampp2p/escrow/src/'
    command = 'node {}rates.js'.format(path)
    return execute_subprocess.apply_async(
                (command,), 
                link=rates_handler.s(
                    currency=currency,
                )
            )