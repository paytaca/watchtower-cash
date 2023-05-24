from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.conf import settings
from typing import Dict

from rampp2p.serializers import TransactionSerializer
from rampp2p.models import Transaction, StatusType, Contract
from rampp2p import utils
import subprocess
import json
import re
import decimal

import logging
logger = logging.getLogger(__name__)

@shared_task(queue='rampp2p__contract_execution')
def execute_subprocess(command):
    # execute subprocess
    logger.warning(f'executing: {command}')
    process = subprocess.Popen(command.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate() 

    stderr = stderr.decode("utf-8")
    stdout = stdout.decode('utf-8')
    logger.warning(f'stdout: {stdout}, stderr: {stderr}')

    if stdout is not None:
        # Define the pattern for matching control characters
        control_char_pattern = re.compile('[\x00-\x1f\x7f-\x9f]')
        
        # Remove all control characters from the JSON string
        clean_stdout = control_char_pattern.sub('', stdout)

        stdout = json.loads(clean_stdout)
    
    response = {'result': stdout, 'error': stderr} 
    logger.warning(f'response: {response}')
    return response

@shared_task(queue='rampp2p__contract_execution')
def handle_subprocess_completion(cmd_resp: Dict, **kwargs):
    data = {
        'result': {
            'message': cmd_resp.get('result'),
            'error': cmd_resp.get('error')
        }
    }
    logger.warning(f'data: {data}')

    action = kwargs.get('action')
    contract_id = kwargs.get('contract_id')
    wallet_hashes = kwargs.get('wallet_hashes')
    success_str = cmd_resp.get('result').get('success')
    success = False if success_str == "False" else bool(success_str)
    
    if bool(success) == True:
        if action == 'create':
            # update contract address
            utils.update_contract_address(contract_id, cmd_resp)
    
        if action == 'refund':
            # create REFUNDED status for order
            status = utils.update_order_status(kwargs.get('order_id'), StatusType.REFUNDED)
            data.get('result')['status'] = status.data

        if action == 'seller-release'  or action == 'arbiter-release':
            # create RELEASED status for order
            status = utils.update_order_status(kwargs.get('order_id'), StatusType.RELEASED)
            data.get('result')['status'] = status.data
    
    data['action'] = action
    data['contract_id'] = contract_id
    
    notify_result(data, wallet_hashes)

@shared_task(queue='rampp2p__contract_execution')
def notify_result(data, wallet_hashes):
    for wallet_hash in wallet_hashes:
        room_name = f'ramp-p2p-updates-{wallet_hash}'
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            room_name,
            {
                'type': 'notify',
                'data': data
            }
        )

# @shared_task(queue='rampp2p__contract_execution')
# def generate_contract(contract_hash: Dict, **kwargs):
#     hash = contract_hash.get('result').get('contract_hash')
#     action = 'create'
#     path = './rampp2p/escrow/src/'
#     command = 'node {}escrow.js contract {} {} {} {}'.format(
#         path,
#         kwargs.get('arbiter_pubkey'), 
#         kwargs.get('buyer_pubkey'), 
#         kwargs.get('seller_pubkey'),
#         hash
#     )
#     return execute_subprocess.apply_async(
#                 (command,), 
#                 link=handle_subprocess_completion.s(
#                         action=action, 
#                         contract_id=kwargs.get('contract_id'), 
#                         wallet_hashes=kwargs.get('wallet_hashes')
#                     )
#             )

@shared_task(queue='rampp2p__contract_execution')
def verify_tx_out(data: Dict, **kwargs):
    '''
    Callback function of subprocess execution that retrieves transaction outputs
    '''
    logger.warning(f'data: {data}')
    logger.warning(f'kwargs: {kwargs}')

    inputs = data.get('result').get('inputs')
    outputs = data.get('result').get('outputs')
    if inputs is None or outputs is None:
        error = data.get('result').get('error')
        return notify_result(
            error,
            kwargs.get('wallet_hashes')
        )
    
    action = kwargs.get('action')
    contract = Contract.objects.get(pk=kwargs.get('contract_id'))
    valid = True

    if action == Transaction.ActionType.FUND:
        fees = utils.get_contract_fees()
        amount = contract.order.crypto_amount + fees

        # one of the outputs must be the contract address
        match_amount = None
        for out in outputs:
            if out.get('address') == contract.contract_address:
                # convert value to decimal (8 decimal places)
                match_amount = decimal.Decimal(out.get('amount'))
                match_amount = match_amount.quantize(decimal.Decimal('0.00000000'))
                break

        # amount must be correct
        if match_amount < amount:
            valid = False
    
    else:
        # sender must be the contract address
        sender_is_contract = False
        for input in inputs:
            if input.get('address') == contract.contract_address:
                sender_is_contract = True
                break
        
        if sender_is_contract == False:
            result = {
                "success": False,
                "error": "contract address not found in tx inputs"
            }
            return notify_result(
                result, 
                kwargs.get('wallet_hashes')
            )
        
        arbiter, buyer, seller, servicer = utils.get_order_peer_addresses(contract.order)
        arbitration_fee = decimal.Decimal(settings.ARBITRATION_FEE).quantize(decimal.Decimal('0.00000000'))/100000000
        trading_fee = decimal.Decimal(settings.TRADING_FEE).quantize(decimal.Decimal('0.00000000'))/100000000
        amount = contract.order.crypto_amount

        arbiter_exists = False
        servicer_exists = False
        buyer_exists = False
        seller_exists = False

        for out in outputs:
            output_address = out.get('address')
            output_amount = decimal.Decimal(out.get('amount')).quantize(decimal.Decimal('0.00000000'))

            # checking for arbiter
            logger.warn(f'output_address: {output_address}, arbiter: {arbiter}')
            logger.warn(f'output_address == arbiter: {output_address == arbiter}')
            if output_address == arbiter:
                if output_amount != arbitration_fee:
                    # found address but incorrect fee
                    logger.warn('arbiter incorrect output_amount')
                    valid = False
                    break
                arbiter_exists = True
            
            # checking for servicer
            if output_address == servicer:    
                if output_amount != trading_fee:
                    # found address but incorrect fee
                    logger.warn('servicer incorrect output_amount')
                    valid = False
                    break
                servicer_exists = True

            if action == Transaction.ActionType.RELEASE:
                # checking for buyer
                if output_address == buyer:
                    if output_amount != amount:
                        # found address but incorrect fee
                        logger.warn('buyer incorrect output_amount')
                        valid = False
                        break
                    buyer_exists = True
                
            if action == Transaction.ActionType.REFUND:
                # checking for seller
                if output_address == seller:
                    if output_amount != amount:
                        # found address but incorrect fee
                        logger.warn('seller incorrect output_amount')
                        valid = False
                        break
                    seller_exists = True
            
        if (not(arbiter_exists and servicer_exists) or
            ((action == Transaction.ActionType.RELEASE and not buyer_exists) or 
            (action == Transaction.ActionType.REFUND and not seller_exists))):
            valid = False

    txdata = None
    status = None
    if valid:
        # update status
        txdata = {
            "action": action,
            "contract_id": contract.id,
            "txid": kwargs.get('txid'),
        }
        tx_serializer = TransactionSerializer(data=txdata)
        if tx_serializer.is_valid():
            tx_serializer = TransactionSerializer(tx_serializer.save())

        status_type = None
        if action == Transaction.ActionType.REFUND:
            status_type = StatusType.REFUNDED
        if action == Transaction.ActionType.RELEASE:
            status_type = StatusType.RELEASED
        if action == Transaction.ActionType.FUND:
            status_type = StatusType.CONFIRMED

        logger.warning(f'status_type: {status_type}')
        status = utils.update_order_status(contract.order.id, status_type).data

    result = {
        "success": valid,
        "status": status,
        "txdata": txdata
    }
    logger.warning(f'result: {result}')

    return notify_result(
        result, 
        kwargs.get('wallet_hashes')
    )