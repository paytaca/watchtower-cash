from celery import shared_task
from typing import Dict
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError

from rampp2p.utils.handler import update_order_status
from rampp2p.utils.websocket import send_order_update
from rampp2p.utils.utils import get_order_peer_addresses, get_trading_fees
from rampp2p.serializers import TransactionSerializer, RecipientSerializer
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
    
    response = {'result': stdout, 'stderr': stderr} 
    logger.warning(f'response: {response}')

    return response

@shared_task(queue='rampp2p__contract_execution')
def handle_transaction(txn: Dict, action: str, contract_id: int):
    '''
    Verifies if `txn` is valid given `action` and `contract_id`.
    Automatically updates the order's status if txn is valid and 
    sends the result through a websocket channel.
    '''
    logger.warning(f'txn: {txn}')
    contract = Contract.objects.get(pk=contract_id)
    valid, error, outputs = verify_txn(action, contract, txn)
    result = None
    
    if valid:
        txn = {
            'valid': valid,
            'error': error,
            'details': {
                'txid': txn.get('details').get('txid'),
                'outputs': outputs,
            }
        }
        result = handle_order_status(action, contract, txn)
    else:
        result = {
            'success': valid,
            'error': error
        }

    send_order_update(
        result, 
        contract.order.id
    )
    return result

# @shared_task(queue='rampp2p__contract_execution')
def handle_order_status(action: str, contract: Contract, txn: Dict): 
    logger.warning(f'>>txn: {txn}')   
    valid = txn.get('valid')
    error = txn.get('error')
    txid = txn.get('details').get('txid')
    outputs = txn.get('details').get('outputs')
    details = txn.get('details')
    logger.warning(f'>>txid: {txid}')
    logger.warning(f'>>txn.details: {details}')

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

        try:
            # Update transaction details 
            transaction = Transaction.objects.get(txid=txid)
            transaction.valid = True

        except Transaction.DoesNotExist as err:
            errors.append(err.args[0])
            result["errors"] = errors
            result["success"] = False
            return result

        # Save transaction outputs
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
                    logger.error(f'recipient_serializer.errors: {recipient_serializer.errors}')
                    result["errors"] = errors
                    result["success"] = False
                    return result
    
        # Update order status
        status_type = None
        if action == Transaction.ActionType.REFUND:
            status_type = StatusType.REFUNDED
        if action == Transaction.ActionType.RELEASE:
            status_type = StatusType.RELEASED
        if action == Transaction.ActionType.ESCROW:
            status_type = StatusType.ESCROWED

        try:
            # If status_type is RELEASED or REFUNDED and order was APPEALED, update the appeal to resolved
            if status_type == StatusType.RELEASED or status_type == StatusType.REFUNDED:
                appeal = Appeal.objects.filter(order=contract.order.id)
                if appeal.exists():
                    appeal = appeal.first()
                    appeal.resolved_at = timezone.now()
                    appeal.save()

            # Update order status
            status = update_order_status(contract.order.id, status_type).data
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
            transaction.verifying = False
            transaction.save()
    
    logger.warning(f'result: {result}')

    return result


# @shared_task(queue='rampp2p__contract_execution')
def verify_txn(action, contract, txn: Dict):
    '''
    Verifies if transaction details (input, outputs, and amounts) satisfy the requisites of its contract.
    '''

    # Logs for debugging
    logger.warning(f'txn: {txn}')

    outputs = []
    error = None
    valid = txn.get('valid')
    if not valid:
        error = txn.get('error')
        return valid, error, outputs

    # # transaction must have at least 1 confirmation
    # confirmations = result.get('confirmations')
    # min_req_confirmations = 1
    # if confirmations != None and confirmations < min_req_confirmations:
    #     error = {"error": f"transaction needs to have at least {min_req_confirmations} confirmations."}
    #     return send_order_update(
    #         error,
    #         contract.order.id
    #     )
    
    txn_details = txn.get('details')
    inputs = txn_details.get('inputs')
    outputs = txn_details.get('outputs')

    # The transaction is invalid, if inputs or outputs are empty
    if inputs is None or outputs is None:
        error = txn.get('error')
        return False, error, None
    
    if action == Transaction.ActionType.ESCROW:
        '''
        If the transaction ActionType is ESCROW, the:
            (1) output value must be correct 
            (2) output address must be the contract address
        '''
        fees, _ = get_trading_fees()
        expected_value = contract.order.crypto_amount + (fees/100000000)

        # Find the output where address = contract address
        actual_value = None
        for output in outputs:
            address = output.get('address')

            if address == contract.address:
                # Get the value transferred and convert to represent 8 decimal places
                actual_value = Decimal(output.get('value'))
                actual_value = actual_value.quantize(Decimal('0.00000000'))/100000000

                outputs.append({
                    "address": address,
                    "value": str(actual_value)
                })
                break

        # Check if the amount is correct
        if actual_value != expected_value:
            valid = False
            error = 'txn value does not match expected value'
    
    else:
        '''
        If the transaction ActionType is RELEASE or REFUND, the:
            (1) input address must be the contract address,
            (2) outputs must include the:
                (i)   servicer address with value == trading fee,
                (ii)  arbiter address with value == arbitration fee,
                (iii) buyer (if RELEASE) or seller (if REFUND) address with correct value minus fees.
        '''
        # Find the contract address in the list of transaction's inputs
        sender_is_contract = False
        for input in inputs:
            address = input.get('address')
            if address == contract.address:
                sender_is_contract = True
                break
        
        # Set valid=False if contract address is not in transaction inputs and return
        if sender_is_contract == False:
            valid = False
            error = 'contract address not found in tx inputs'
            return valid, error, outputs
        
        # Retrieve expected transaction output addresses
        arbiter_addr, buyer_addr, seller_addr, servicer_addr = get_order_peer_addresses(contract.order)

        # Calculate expected transaction amount and fees
        arbitration_fee = Decimal(settings.ARBITRATION_FEE).quantize(Decimal('0.00000000'))/100000000
        service_fee = Decimal(settings.SERVICE_FEE).quantize(Decimal('0.00000000'))/100000000
        expected_value = Decimal(contract.order.crypto_amount).quantize(Decimal('0.00000000'))
        
        arbiter_exists = False
        servicer_exists = False
        buyer_exists = False
        seller_exists = False

        for output in outputs:
            address = output.get('address')
            actual_value = Decimal(output.get('value')).quantize(Decimal('0.00000000'))/100000000
            
            # Checks if the current address is the arbiter
            # and set valid=False if fee is incorrect
            if address == arbiter_addr:
                if actual_value != arbitration_fee:
                    valid = False
                    error = 'incorrect arbiter output value'
                    logger.warning(f'actual_value: {actual_value} | arbitration_fee: {arbitration_fee}')
                    logger.warning(f'[validate_txn] error: {error}')
                    break
                arbiter_exists = True
            
            # Checks if the current address is the servicer 
            # and set valid=False if fee is incorrect
            if address == servicer_addr:    
                if actual_value != service_fee:
                    valid = False
                    error = 'incorrect servicer output value'
                    logger.warning(f'actual_value: {actual_value} | service_fee: {service_fee}')
                    logger.warning(f'[validate_txn] error: {error}')
                    break
                servicer_exists = True

            if action == Transaction.ActionType.RELEASE:
                # If the action type is RELEASE, check if the address is the buyer
                # and if the value is correct
                if address == buyer_addr:
                    if actual_value != expected_value:
                        error = 'incorrect buyer output value'
                        logger.warning(f'typeof actual_value: {type(actual_value)}')
                        logger.warning(f'typeof expected_value: {type(expected_value)}')
                        logger.warning(f'actual_value: {actual_value} | expected_value: {expected_value}')
                        logger.warning(f'[validate_txn] error: {error}')
                        valid = False
                        break
                    buyer_exists = True
                
            if action == Transaction.ActionType.REFUND:
                # If the action type is REFUND, check if the address is the seller
                # and if the value is correct
                if address == seller_addr:
                    if actual_value != expected_value:
                        error = 'incorrect seller output value'
                        logger.warning(f'actual_value: {actual_value} | expected_value: {expected_value}')
                        logger.warning(f'[validate_txn] error: {error}')
                        valid = False
                        break
                    seller_exists = True
        
        '''
        Transaction is not valid if:
            (1) the arbiter or servicer is not found in the outputs, or
            (2) the transaction is for RELEASE but the buyer was not found, or
            (3) the transaction is for REFUND but the seller was not found
        '''
        if (not(arbiter_exists and servicer_exists) or
            ((action == Transaction.ActionType.RELEASE and not buyer_exists) or 
            (action == Transaction.ActionType.REFUND and not seller_exists))):
            valid = False
    
    return valid, error, outputs