from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from rampp2p.models import Contract
from rampp2p.utils import websocket
import subprocess
import json

import logging
logger = logging.getLogger(__name__)

@shared_task(queue='rampp2p__contract_execution')
def execute_subprocess(command):
    # execute subprocess
    process = subprocess.Popen(command.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate() 
    stderr = stderr.decode("utf-8")
    stdout = stdout.decode('utf-8')
    stdout = stdout.rstrip().replace('\n', '')
    stdout = stdout.replace('\\', '')
    stdout = json.loads(stdout)
    response = {'result': stdout, 'error': stderr} 
    return response

@shared_task(queue='rampp2p__contract_execution')
def notify_subprocess_completion(response, **kwargs):
    action = kwargs.get('action')
    contract_id = kwargs.get('contract_id')
    wallet_hash = kwargs.get('wallet_hash')

    if action == 'create':
        # update contract address
        contract_address = response.get('result').get('contract_address')
        contract_obj = Contract.objects.get(pk=contract_id)
        contract_obj.contract_address = contract_address
        contract_obj.save()

    room_name = f'ramp-p2p-updates-{wallet_hash}'
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        room_name,
        {
            'type': 'notify',
            'message': response
        }
    )