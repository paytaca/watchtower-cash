from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from typing import Dict, List

from rampp2p.serializers import StatusSerializer
from rampp2p.models import Contract, StatusType
import subprocess
import json
import re

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
def notify_subprocess_completion(cmd_resp: Dict, **kwargs):
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
            update_contract_address(contract_id, cmd_resp)
    
        if action == 'refund':
            # create REFUNDED status for order
            status = update_order_status(kwargs.get('order_id'), StatusType.REFUNDED)
            data.get('result')['status'] = status.data

        if action == 'seller-release'  or action == 'arbiter-release':
            # create RELEASED status for order
            status = update_order_status(kwargs.get('order_id'), StatusType.RELEASED)
            data.get('result')['status'] = status.data
    
    data['action'] = action
    data['contract_id'] = contract_id

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

@shared_task(queue='rampp2p__contract_execution')
def generate_contract(contract_hash: Dict, **kwargs):
    hash = contract_hash.get('result').get('contract_hash')
    action = 'create'
    path = './rampp2p/escrow/src/'
    command = 'node {}escrow.js contract {} {} {} {}'.format(
        path,
        kwargs.get('arbiter_pubkey'), 
        kwargs.get('buyer_pubkey'), 
        kwargs.get('seller_pubkey'),
        hash
    )
    return execute_subprocess.apply_async(
                (command,), 
                link=notify_subprocess_completion.s(
                        action=action, 
                        contract_id=kwargs.get('contract_id'), 
                        wallet_hashes=kwargs.get('wallet_hashes')
                    )
            )

def update_contract_address(contract_id, data):
    contract_address = data.get('result').get('contract_address')
    contract = Contract.objects.get(pk=contract_id)
    contract.contract_address = contract_address
    contract.save()