from celery import shared_task
from typing import Dict
from rampp2p.utils.websocket import send_order_update
from main.utils.subscription import save_subscription
from rampp2p.models import Contract
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

    if stdout is not None:
        # Define the pattern for matching control characters
        control_char_pattern = re.compile('[\x00-\x1f\x7f-\x9f]')
        
        # Remove all control characters from the JSON string
        clean_stdout = control_char_pattern.sub('', stdout)

        stdout = json.loads(clean_stdout)
    
    response = {'result': stdout, 'error': stderr}

    return response

@shared_task(queue='rampp2p__contract_execution')
def contract_handler(response: Dict, **kwargs):
    data = response.get('result')
    data['error'] = response.get('error')

    order_id = kwargs.get('order_id')
    success = response.get('result').get('success')
    success = False if success == "False" else bool(success)

    if bool(success) == True:
        # update the order's contract address
        address = data.get('contract_address')
        contract = Contract.objects.get(order__id=order_id)
        contract.address = address
        contract.save()

        # Subscribe to contract address
        created = save_subscription(contract.address, contract.id)
        if created: logger.warn(f'Subscribed to contract {contract.address}')
    
    return send_order_update(data, contract.order.id)