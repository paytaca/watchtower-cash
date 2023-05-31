from django.conf import settings
import decimal

import rampp2p.tasks as tasks

import logging
logger = logging.getLogger(__name__)

def create(**kwargs):
    action = 'CREATE'
    path = './rampp2p/escrow/src/'
    command = 'node {}escrow.js {} {} {} {}'.format(
        path,        
        kwargs.get('arbiter_pubkey'), 
        kwargs.get('buyer_pubkey'), 
        kwargs.get('seller_pubkey'),
        kwargs.get('timestamp'),
    )
    return tasks.execute_subprocess.apply_async(
                (command,), 
                link=tasks.handle_subprocess_completion.s(
                    action=action, 
                    order_id=kwargs.get('order_id')
                )
            )

def get_contract_fees():
    hardcoded_fee = decimal.Decimal(settings.HARDCODED_FEE)
    arbitration_fee = decimal.Decimal(settings.ARBITRATION_FEE)
    trading_fee = decimal.Decimal(settings.TRADING_FEE)
    total_fee = hardcoded_fee + arbitration_fee + trading_fee
    decimal_fee = total_fee/100000000
    return decimal_fee