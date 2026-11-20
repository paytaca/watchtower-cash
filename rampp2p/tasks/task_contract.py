from celery import shared_task
from typing import Dict
from rampp2p.utils.websocket import send_order_update
from main.utils.subscription import save_subscription
from rampp2p.models import Contract
from rampp2p.contract_access import order_is_canceled, canceled_contract_payload
from rampp2p.contract_generation import generate_contract_address

import logging
logger = logging.getLogger(__name__)

@shared_task(queue='rampp2p__contract_execution')
def generate_contract(arbiter_pubkey, buyer_pubkey, seller_pubkey,
                      timestamp, service_fee, arbitration_fee):
    return generate_contract_address(
        arbiter_pubkey, buyer_pubkey, seller_pubkey,
        timestamp, service_fee, arbitration_fee,
    )

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
    if order_is_canceled(order_id):
        return send_order_update(canceled_contract_payload(), order_id)
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
    
    # Cancellation may have happened while persisting/subscribing the address.
    if order_is_canceled(order_id):
        return send_order_update(canceled_contract_payload(), order_id)
    return send_order_update(data, order_id)
