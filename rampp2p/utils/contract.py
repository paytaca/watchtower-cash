import rampp2p.tasks as tasks
from typing import List

import logging
logger = logging.getLogger(__name__)

def create(contract_id: int, wallet_hashes: List, **kwargs):
    path = './rampp2p/escrow/src/'
    command = 'node {}hash.js'.format(path)
    return tasks.execute_subprocess.apply_async(
                (command,), 
                link=tasks.generate_contract.s(
                        contract_id=contract_id,
                        wallet_hashes=wallet_hashes,
                        **kwargs
                    )
            )

def release(order_id: int, contract_id: int, wallet_hashes: List, **kwargs):     
    action = kwargs.get('action')
    path = './rampp2p/escrow/src/'
    command = 'node {}escrow.js {} {} {} {} {} {} {} {} {} {}'.format(
        path,
        action,
        kwargs.get('arbiter_pubkey'),  
        kwargs.get('buyer_pubkey'),
        kwargs.get('seller_pubkey'),
        kwargs.get('contract_hash'),
        kwargs.get('caller_pubkey'),
        kwargs.get('caller_sig'),
        kwargs.get('recipient_address'),
        kwargs.get('arbiter_address'),
        kwargs.get('amount'),
    )
    return tasks.execute_subprocess.apply_async(
                (command,), 
                link=tasks.notify_subprocess_completion.s(
                    action=action, 
                    order_id=order_id,
                    contract_id=contract_id, 
                    wallet_hashes=wallet_hashes,
                )
            )

def refund(order_id: int, contract_id: int, wallet_hashes: List, **kwargs):
    action = 'refund'
    path = './rampp2p/escrow/src/'
    command = 'node {}escrow.js {} {} {} {} {} {} {} {} {} {}'.format(
        path,
        action,
        kwargs.get('arbiter_pubkey'),
        kwargs.get('buyer_pubkey'), 
        kwargs.get('seller_pubkey'),
        kwargs.get('contract_hash'), 
        kwargs.get('caller_pubkey'),
        kwargs.get('caller_sig'),
        kwargs.get('recipient_address'),
        kwargs.get('arbiter_address'),
        kwargs.get('amount'),
    )

    return tasks.execute_subprocess.apply_async(
                (command,), 
                link=tasks.notify_subprocess_completion.s(
                    action=action, 
                    order_id=order_id,
                    contract_id=contract_id, 
                    wallet_hashes=wallet_hashes,
                )
            )

class ContractError(Exception):
    def __init__(self, message):
        self.message = message
    
    def __str__(self):
        return self.message