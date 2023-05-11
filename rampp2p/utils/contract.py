from django.conf import settings
import rampp2p.tasks as tasks
from typing import List

import logging
logger = logging.getLogger(__name__)

def create(contract_id: int, wallet_hash: str, **kwargs):
    action = 'create'
    path = './rampp2p/escrow/src/'
    command = 'node {}escrow.js contract {} {} {}'.format(
        path,
        kwargs.get('arbiterPubkey'), 
        kwargs.get('buyerPubkey'), 
        kwargs.get('sellerPubkey')
    )
    return tasks.execute_subprocess.apply_async(
                (command,), 
                link=tasks.notify_subprocess_completion.s(
                        action=action, 
                        contract_id=contract_id, 
                        wallet_hashes=[wallet_hash]
                    )
            )

def release(order_id: int, contract_id: int, wallet_hashes: List, **kwargs):     
    action = kwargs.get('action')
    path = './rampp2p/escrow/src/'
    command = 'node {}escrow.js {} {} {} {} {} {} {} {}'.format(
        path,
        action,
        kwargs.get('arbiterPubkey'),  
        kwargs.get('buyerPubkey'),
        kwargs.get('sellerPubkey'),
        kwargs.get('callerSig'),
        kwargs.get('recipientAddr'),
        kwargs.get('arbiterAddr'),
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
    command = 'node {}escrow.js {} {} {} {} {} {} {} {}'.format(
        path,
        action,
        kwargs.get('arbiterPubkey'),
        kwargs.get('buyerPubkey'), 
        kwargs.get('sellerPubkey'), 
        kwargs.get('callerSig'),
        kwargs.get('recipientAddr'),
        kwargs.get('arbiterAddr'),
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