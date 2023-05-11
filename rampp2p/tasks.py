from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from typing import Dict

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

    if action == 'create':
        # update contract address
        contract_address = cmd_resp.get('result').get('contract_address')
        contract_obj = Contract.objects.get(pk=contract_id)
        contract_obj.contract_address = contract_address
        contract_obj.save()
    
    if action == 'refund':
        if bool(success) == True:
            # create REFUNDED status for order
            order_id = kwargs.get('order_id')
            serializer = StatusSerializer(data={
                'status': StatusType.REFUNDED,
                'order': order_id
            })
            
            if serializer.is_valid():
                status = StatusSerializer(serializer.save())
                data.get('result')['status'] = status.data

    if action == 'seller-release'  or action == 'arbiter-release':
        # create RELEASED status for order
        logger.warning(f'success: {success}, bool(success): {bool(success)}')
        if bool(success) == True:
            order_id = kwargs.get('order_id')
            serializer = StatusSerializer(data={
                'status': StatusType.RELEASED, 
                'order': order_id
            })
            if serializer.is_valid():
                status = StatusSerializer(serializer.save())
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