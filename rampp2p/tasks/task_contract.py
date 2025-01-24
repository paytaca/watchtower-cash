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
def execute_subprocess(command):
    """
    Executes a subprocess command.

    This function runs a subprocess command and captures its output and error streams.
    It also removes control characters from the JSON output.

    Args:
        command (str): The command to be executed.

    Returns:
        dict: A dictionary containing the result and stderr output of the command.
    """
    # execute subprocess
    logger.warning(f'executing: {command}')
    process = subprocess.Popen(command.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate() 
    logger.warn(f'stdout: {stdout}')
    logger.warn(f'stderr: {stderr}')
    
    if stderr is not None:
        stderr = stderr.decode("utf-8") 
    
    if stdout is not None:
        stdout = stdout.decode('utf-8')

    if stdout is not None:
        # Define the pattern for matching control characters
        control_char_pattern = re.compile('[\x00-\x1f\x7f-\x9f]')
        
        # Remove all control characters from the JSON string
        clean_stdout = control_char_pattern.sub('', stdout)

        if clean_stdout is not None:
            stdout = json.loads(clean_stdout)
    
    response = {'result': stdout, 'error': stderr}

    return response

@shared_task(queue='rampp2p__contract_execution')
def contract_handler(response: Dict, **kwargs):
    """
    Handles the contract creation response.

    This function processes the response from the contract creation subprocess.
    If the contract creation is successful, it updates the contract address and subscribes to it
    for incoming/outgoing transactions.
    It also sends the result through a websocket channel.

    Args:
        response (Dict): The response from the contract creation subprocess.
        **kwargs: Additional keyword arguments, including the order ID.

    Returns:
        None
    """
    data = response.get('result')
    order_id = kwargs.get('order_id')
    success = response.get('result').get('success')
    success = False if success == "false" else bool(success)

    if bool(success) == True:
        # update the order's contract address
        address = data.get('contract_address')
        contract = Contract.objects.get(order__id=order_id)
        contract.address = address
        contract.save()

        # Subscribe to contract address
        created = save_subscription(contract.address, contract.id)
        if created: logger.warn(f'Subscribed to contract {contract.address}')
    else:
        data['error'] = response.get('error')
    
    return send_order_update(data, contract.order.id)