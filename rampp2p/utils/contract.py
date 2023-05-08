from django.conf import settings
import rampp2p.tasks as tasks
from rampp2p.utils import websocket

import logging
logger = logging.getLogger(__name__)

def create(wallet_hash: str, **kwargs):
    path = './rampp2p/escrow/src/'
    command = 'node {}escrow.js contract {} {} {}'.format(
        path,
        kwargs.get('arbiterPubkey'), 
        kwargs.get('buyerPubkey'), 
        kwargs.get('sellerPubkey')
    )
    return tasks.execute_subprocess.apply_async((command,), link=tasks.notify_subprocess_completion.s(wallet_hash=wallet_hash))

def release(**kwargs):        
    path = './rampp2p/escrow/src/'
    command = 'node {}escrow.js {} {} {} {} {} {} {} {}'.format(
        path,
        kwargs.get('action'),
        kwargs.get('arbiterPubkey'), 
        kwargs.get('sellerPubkey'), 
        kwargs.get('buyerPubkey'),
        kwargs.get('callerSig'),
        kwargs.get('recipientAddr'),
        kwargs.get('arbiterAddr'),
        kwargs.get('amount'),
    )
    return tasks.execute_subprocess(command)

def refund(**kwargs):
    path = './rampp2p/escrow/src/'
    command = 'node {}escrow.js refund {} {} {} {} {} {} {}'.format(
        path,
        kwargs.get('arbiterPubkey'), 
        kwargs.get('sellerPubkey'), 
        kwargs.get('buyerPubkey'),
        kwargs.get('callerSig'),
        kwargs.get('recipientAddr'),
        kwargs.get('arbiterAddr'),
        kwargs.get('amount'),
    )
    return tasks.execute_subprocess(command)

class ContractError(Exception):
    def __init__(self, message):
        self.message = message
    
    def __str__(self):
        return self.message