from celery import shared_task
from typing import Dict
from main.utils.subscription import new_subscription
from rampp2p.utils.websocket import send_order_update
from rampp2p.utils.handler import update_order_status
from rampp2p.models import Contract, StatusType
from django.core.exceptions import ValidationError

import subprocess
import json
import re

import logging
logger = logging.getLogger(__name__)

@shared_task(queue='rampp2p__contract_execution')
def execute_subprocess(command, **kwargs):
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
def contract_handler(response: Dict, **kwargs):
    data = response.get('result')
    data['error'] = response.get('error')
    logger.warning(f'data: {data}')

    order_id = kwargs.get('order_id')
    success = response.get('result').get('success')
    success = False if success == "False" else bool(success)

    if bool(success) == True:
        # # update order status to ESCROW_PENDING
        # try:
        #     update_order_status(order_id, StatusType.ESCROW_PENDING)
        # except ValidationError as err:
        #     logger.error(err)
        #     return send_order_update(err, contract.order.id)
        
        # update the order's contract address
        address = data.get('contract_address')
        contract = Contract.objects.get(order__id=order_id)
        contract.address = address
        contract.save()

        # TODO: subscribe to contract address: listen for incoming & outgoing utxo
        new_subscription(address=address)
    
    return send_order_update(data, contract.order.id)