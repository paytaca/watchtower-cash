from rampp2p.tasks.market_rate_tasks import execute_subprocess, rates_request_handler

import logging
logger = logging.getLogger(__name__)

def get_rates_request(currency):
    '''
    Returns the current price of BCH in the specified currency or several different currencies.
    '''
    logger.warning('Retrieving the market price of BCH')
    path = './rampp2p/escrow/src/'
    command = 'node {}rates.js'.format(path)
    return execute_subprocess.apply_async(
                (command,), 
                link=rates_request_handler.s(
                    currency=currency,
                )
            )