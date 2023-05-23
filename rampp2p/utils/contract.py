from django.conf import settings
from typing import List
import decimal

import rampp2p.tasks as tasks
from rampp2p.models import Contract

import logging
logger = logging.getLogger(__name__)

def create(contract_id: int, wallet_hashes: List, **kwargs):
    action = 'create'
    path = './rampp2p/escrow/src/'
    command = 'node {}escrow.js contract {} {} {}'.format(
        path,
        kwargs.get('arbiter_pubkey'), 
        kwargs.get('buyer_pubkey'), 
        kwargs.get('seller_pubkey')
    )
    return tasks.execute_subprocess.apply_async(
                (command,), 
                link=tasks.handle_subprocess_completion.s(
                        action=action, 
                        contract_id=contract_id, 
                        wallet_hashes=wallet_hashes
                    )
            )

def release(order_id: int, contract_id: int, wallet_hashes: List, **kwargs):     
    action = kwargs.get('action')
    path = './rampp2p/escrow/src/'
    command = 'node {}escrow.js {} {} {} {} {} {} {} {} {}'.format(
        path,
        action,
        kwargs.get('arbiter_pubkey'),  
        kwargs.get('buyer_pubkey'),
        kwargs.get('seller_pubkey'),
        kwargs.get('caller_pubkey'),
        kwargs.get('caller_sig'),
        kwargs.get('recipient_address'),
        kwargs.get('arbiter_address'),
        kwargs.get('amount'),
    )
    return tasks.execute_subprocess.apply_async(
                (command,), 
                link=tasks.handle_subprocess_completion.s(
                    action=action, 
                    order_id=order_id,
                    contract_id=contract_id, 
                    wallet_hashes=wallet_hashes,
                )
            )

def refund(order_id: int, contract_id: int, wallet_hashes: List, **kwargs):
    action = 'refund'
    path = './rampp2p/escrow/src/'
    command = 'node {}escrow.js {} {} {} {} {} {} {} {} {}'.format(
        path,
        action,
        kwargs.get('arbiter_pubkey'),
        kwargs.get('buyer_pubkey'), 
        kwargs.get('seller_pubkey'),
        kwargs.get('caller_pubkey'),
        kwargs.get('caller_sig'),
        kwargs.get('recipient_address'),
        kwargs.get('arbiter_address'),
        kwargs.get('amount'),
    )

    return tasks.execute_subprocess.apply_async(
                (command,), 
                link=tasks.handle_subprocess_completion.s(
                    action=action, 
                    order_id=order_id,
                    contract_id=contract_id, 
                    wallet_hashes=wallet_hashes,
                )
            )

def get_contract_fees():
    hardcoded_fee = decimal.Decimal(settings.HARDCODED_FEE)
    arbitration_fee = decimal.Decimal(settings.ARBITRATION_FEE)
    trading_fee = decimal.Decimal(settings.TRADING_FEE)
    total_fee = hardcoded_fee + arbitration_fee + trading_fee
    decimal_fee = total_fee/100000000
    return decimal_fee


def update_contract_address(contract_id, data):
    contract_address = data.get('result').get('contract_address')
    contract = Contract.objects.get(pk=contract_id)
    contract.contract_address = contract_address
    contract.save()