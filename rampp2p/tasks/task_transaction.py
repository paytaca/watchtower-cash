from celery import shared_task
from typing import Dict
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Q

from rampp2p.utils import bch_to_satoshi
from rampp2p.utils.handler import update_order_status
from rampp2p.utils.notifications import send_push_notification
import rampp2p.utils.websocket as websocket

from rampp2p.serializers import RecipientSerializer
from main.models import Subscription
from rampp2p.models import (
    Transaction, 
    StatusType, 
    Contract,
    Appeal
)

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

    stderr = stderr.decode("utf-8")
    stdout = stdout.decode('utf-8')

    if stdout is not None:
        # Define the pattern for matching control characters
        control_char_pattern = re.compile('[\x00-\x1f\x7f-\x9f]')
        
        # Remove all control characters from the JSON string
        clean_stdout = control_char_pattern.sub('', stdout)

        stdout = json.loads(clean_stdout)
    
    response = {'result': stdout, 'stderr': stderr} 

    return response    

@shared_task(queue='rampp2p__contract_execution')
def handle_transaction_validation(txn: Dict, action: str, contract_id: int):
    """
    Validates a transaction for a given action and contract.

    This function checks if the transaction is valid for the specified action and contract.
    If valid, it updates the related order's status and sends the result through a websocket channel.

    Args:
        txn (Dict): The transaction details.
        action (str): The action type (e.g., 'ESCROW', 'REFUND', 'RELEASE').
        contract_id (int): The ID of the contract associated with the transaction.

    Returns:
        dict: The result of the validation and order status update.
    """
    logger.warning(f'Validating txn: {txn} | {action} | contract: {contract_id}')

    # Fetches contract given contract id
    contract = Contract.objects.get(pk=contract_id)
    # Validates the transaction
    valid, error, outputs = verify_txn(action, contract, txn)
    result = None
    
    # Builds the result response
    if valid:
        txn = {
            'action': action,
            'valid': valid,
            'error': error,
            'details': {
                'txid': txn.get('details').get('txid'),
                'outputs': outputs,
            }
        }
        # Updates the contract related order's status
        result = handle_order_status(action, contract, txn)
    else:
        result = {
            'action': action,
            'success': valid,
            'error': error
        }

    # Sends the result response through websocket
    websocket.send_order_update(
        result, 
        contract.order.id
    )

    return result

def handle_order_status(action: str, contract: Contract, txn: Dict):
    """
    Handles the order status update based on the transaction action.

    This function updates the order status and transaction details based on the action type.
    It also sends push notifications to the contract parties and removes address tx subscriptions if necessary.

    Args:
        action      (str): The action type (e.g., 'ESCROW', 'REFUND', 'RELEASE').
        contract    (Contract): The contract associated with the transaction.
        txn         (Dict): The transaction details.

    Returns:
        dict: The result of the order status update.
    """
    valid = txn.get('valid')
    error = txn.get('error')
    txid = txn.get('details').get('txid')
    outputs = txn.get('details').get('outputs')

    errors = []
    if error is not None:
        errors.append(error)

    result = {
        "success": valid
    }
    txdata = {
        "action": action,
        "txid": txid,
        "contract": contract.id
    }

    status = None
    if valid:

        # Update transaction txid and valid status
        transaction = Transaction.objects.filter(Q(contract__id=contract.id) & Q(action=action))
        if transaction.exists():
            transaction = transaction.last()
            transaction.valid = True
            transaction.txid = txid
        else:
            transaction = Transaction.objects.create(
                txid=txid,
                valid=True,
                contract=contract,
                action=action
            )

        # Save transaction outputs as Recipients
        if outputs is not None:
            for output in outputs:
                out_data = {
                    "transaction": transaction.id,
                    "address": output.get('address'),
                    "value": output.get('value')
                }
                recipient_serializer = RecipientSerializer(data=out_data)
                if recipient_serializer.is_valid():
                    recipient_serializer = RecipientSerializer(recipient_serializer.save())
                else:
                    result["errors"] = errors
                    result["success"] = False
                    return result
    
        # Update the status of the associated order
        order_members = contract.order.get_members()
        status_created_by = None
        status_type = None
        if action == Transaction.ActionType.REFUND:
            status_created_by = order_members['arbiter'].wallet_hash
            status_type = StatusType.REFUNDED
        if action == Transaction.ActionType.RELEASE:
            status_type = StatusType.RELEASED
        if action == Transaction.ActionType.ESCROW:
            status_created_by = order_members['seller'].wallet_hash
            status_type = StatusType.ESCROWED

        try:
            # Resolve order appeal (if any) once order is released/refunded
            appeal_exists = False
            if status_type == StatusType.RELEASED or status_type == StatusType.REFUNDED:
                appeal = Appeal.objects.filter(order=contract.order.id)
                appeal_exists = appeal.exists()
                if appeal_exists:
                    appeal = appeal.first()
                    appeal.resolved_at = timezone.now()
                    appeal.save()

            # Update order appealable_at if status is escrowed
            if status_type == StatusType.ESCROWED:
                contract.order.appealable_at = timezone.now() + contract.order.ad_snapshot.appeal_cooldown
                contract.order.save()

            # Update order status
            status = update_order_status(contract.order.id, status_type, wallet_hash=status_created_by).data
            if contract.order.is_cash_in:
                websocket.send_cashin_order_alert({'type': 'ORDER_STATUS_UPDATED', 'order': contract.order.id}, contract.order.owner.wallet_hash)

            # Remove address subscription once order is complete
            if status_type == StatusType.RELEASED or status_type == StatusType.REFUNDED:
                logger.info(f'Removing subscription to contract {transaction.contract.address}')
                remove_subscription(transaction.contract.address, transaction.contract.id)

            # Send push notifications to contract parties
            party_a = contract.order.owner.wallet_hash
            party_b = contract.order.ad_snapshot.ad.owner.wallet_hash
            recipients = [party_a, party_b]
            if appeal_exists:
                recipients.append(contract.order.arbiter.wallet_hash)
            message = f'Order #{contract.order.id} {status_type.label.lower()}'
            send_push_notification(recipients, message, extra={ 'order_id': contract.order.id })

        except ValidationError as err:
            errors.append(err.args[0])
            result["errors"] = errors
            result["success"] = False
            return result

        txdata["outputs"] = outputs
        txdata["errors"] = errors
        result["status"] = status
        result["txdata"] = txdata

        if result["success"]:
            transaction.save()
    
    return result

class TxnVerificationError(Exception):
    def __init__(self, message, error_code=None, transaction_id=None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.transaction_id = transaction_id

    def __str__(self):
        details = f"{self.message}"
        if self.error_code:
            details += f" (Error Code: {self.error_code})"
        if self.transaction_id:
            details += f" (Transaction ID: {self.transaction_id})"
        return details


def verify_txn(action, contract: Contract, txn: Dict):
    """
    Verifies the validity of a transaction for a given action and contract.

    This function checks the transaction inputs and outputs to ensure they match the expected values
    for the specified action and contract.

    Args:
        action   (str): The action type (e.g., 'ESCROW', 'REFUND', 'RELEASE').
        contract (Contract): The contract associated with the transaction.
        txn      (Dict): The transaction details.

    Returns:
        tuple: A tuple containing the validity status, error message (if any), and transaction outputs.
    """
    outputs = []
    try:
        if txn.get('valid') is False:
            raise TxnVerificationError(txn.get('error', 'Transaction invalid or may still be unconfirmed in the blockchain. Please try again later.'))
        
        txn_details = txn.get('details')
        inputs = txn_details.get('inputs')
        outputs = txn_details.get('outputs')

        # The transaction is invalid, if inputs or outputs are empty
        if not inputs or not outputs:
            raise TxnVerificationError(txn.get('error', 'Transaction input/outputs empty'))
        
        if action == Transaction.ActionType.ESCROW:
            # If the transaction ActionType is ESCROW:
            #  1) check if output amount is correct,
            #  2) check if output address is the expected contract address
            
            total_fees = contract.get_total_fees()
            if total_fees is None:
                raise TxnVerificationError(f'Failed to fetch correct total_fees expected an int got {total_fees}')
            
            # Calculate expected amount in satoshi including fees
            expected_amount = contract.order.trade_amount
            if expected_amount is None:
                expected_amount = bch_to_satoshi(contract.order.crypto_amount)
            expected_amount_with_fees = expected_amount + total_fees

            if len(outputs) >= 1:
                to_address = outputs[0].get('address')
                # Check if the tx destination address is the contract address
                if to_address == contract.address:
                    # Check if the tx amount and expected amount matches
                    actual_amount = outputs[0].get('value')
                    if actual_amount != expected_amount_with_fees:
                        raise TxnVerificationError(f'Transaction value {actual_amount} does not match expected value {expected_amount_with_fees}')
                else:
                    raise TxnVerificationError(f'Transaction outputs[0] address {outputs[0].get("address")} does not match expected contract address {contract.address}')
            else:
                raise TxnVerificationError(f'Empty transaction outputs')
        
        else:
            # If the transaction ActionType is RELEASE or REFUND:
            # (1) check if input address is the contract address
            # (2) check if outputs include:
            #    - servicer address with output amount == service fee
            #    - arbiter address with output amount == arbitration fee
            #    - buyer (if RELEASE) or seller (if REFUND) address with correct value minus fees.

            # Find the contract address in the list of transaction's inputs
            input_addresses = [item['address'] for item in inputs if 'address' in item]
            if contract.address not in input_addresses:
                raise TxnVerificationError(f'Expected contract address {contract.address} not found in input_addresses: {input_addresses}')
            
            # Retrieve the expected transaction output addresses
            contract_members = contract.get_members()
            expected_addresses = {
                'arbiter': contract_members['arbiter'].address,
                'buyer': contract_members['buyer'].address,
                'seller': contract_members['seller'].address,
                'servicer': settings.SERVICER_ADDR
            }

            # Calculate the expected transaction amount in satoshi, including fees
            expected_arbitration_fee = contract.arbitration_fee
            expected_service_fee = contract.service_fee
            expected_transfer_amount = contract.order.trade_amount
            if expected_transfer_amount is None:
                expected_transfer_amount = bch_to_satoshi(contract.order.crypto_amount)

            if len(outputs) >= 3:
                transferred_amount = int(outputs[0].get('value'))
                to_address = outputs[0].get('address')

                if action == Transaction.ActionType.RELEASE:
                    expected_address = expected_addresses['buyer']
                if action == Transaction.ActionType.REFUND:
                    expected_address = expected_addresses['seller']
                
                if to_address == expected_address:
                    if transferred_amount != expected_transfer_amount:
                        raise TxnVerificationError(f'Incorrect output value {transferred_amount} (expected {expected_transfer_amount})')
                else:
                    raise TxnVerificationError(f'Incorrect output address {to_address} (expected {expected_address})')

                # Checks if outputs[1] sends to servicer and if amount sent is correct
                servicer_address = outputs[1].get('address')
                if servicer_address == expected_addresses['servicer']:
                    service_fee = outputs[1].get('value')
                    if service_fee != expected_service_fee:
                        raise TxnVerificationError(f'Incorrect service output value {service_fee} (expected {expected_service_fee})')
                else:
                    raise TxnVerificationError(f'Incorrect service address {servicer_address} (expected {expected_addresses["servicer"]})')

                # Checks if outputs[2] sends to arbiter and if amount sent is correct
                arbiter_address = outputs[2].get('address')
                if arbiter_address == expected_addresses['arbiter']:
                    arbitration_fee = int(outputs[2].get('value'))
                    if arbitration_fee != expected_arbitration_fee:
                        raise TxnVerificationError(f'Incorrect arbiter output value {arbitration_fee} (expected {expected_arbitration_fee})')
                else:
                    raise TxnVerificationError(f'Incorrect arbiter address {arbiter_address} (expected {expected_addresses["arbiter"]})')
        
        return True, None, outputs
    except TxnVerificationError as err:
        logger.exception(err.message)
        return False, err.message, outputs

def remove_subscription(address, subscriber_id):
    """
    Removes a subscription for a given address and subscriber.

    This function deletes the subscription record for the specified address and subscriber ID.

    Args:
        address (str): The address of the subscription.
        subscriber_id (int): The ID of the subscriber.

    Returns:
        bool: True if the subscription was removed, False otherwise.
    """
    subscription = Subscription.objects.filter(
        address__address=address,
        recipient__telegram_id=subscriber_id
    )
    if subscription.exists():
        subscription.delete()
        return True
    return False