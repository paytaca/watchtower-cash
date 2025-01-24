from rampp2p.tasks.task_contract import execute_subprocess, contract_handler

import logging
logger = logging.getLogger(__name__)

def create_contract(**kwargs):
    '''
    Executes a subprocess task to generate the contract address
    '''
    path = './rampp2p/js/src/'
    command = 'node {}escrow.js {} {} {} {} {} {}'.format(
        path,        
        kwargs.get('arbiter_pubkey'), 
        kwargs.get('buyer_pubkey'), 
        kwargs.get('seller_pubkey'),
        kwargs.get('timestamp'),
        kwargs.get('service_fee'),
        kwargs.get('arbitration_fee')
    )
    logger.warning(f'service_fee: {kwargs.get("service_fee")} | arbitration_fee: {kwargs.get("arbitration_fee")}')
    logger.warning(f'command: {command}')

    return execute_subprocess.apply_async(
        (command,), 
        link=contract_handler.s(
            order_id=kwargs.get('order_id')
        )
    )
