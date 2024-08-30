from rampp2p.tasks.transaction_tasks import execute_subprocess, handle_transaction_validation
from django.conf import settings
from rampp2p.models import Transaction
from main.utils.queries.node import Node
import requests

import logging
logger = logging.getLogger(__name__)

def process_transaction(txid, output_address, inputs=None):
    logger.warn(f'RampP2P processing tx {txid}')
    try:
        pending_transactions = Transaction.objects.filter(txid__isnull=True)
        transaction = pending_transactions.filter(contract__address=output_address)
        if transaction.exists():
            '''ESCROW transaction: pending (txid=null) `Transaction` where 
            contract address is an output address of the transaction'''
            transaction = transaction.first()
            validate_transaction(txid, Transaction.ActionType.ESCROW, transaction.contract.id)
        else:
            '''RELEASE/REFUND transaction: pending (txid=null) `Transaction` where 
            contract address is an input address of the transaction'''
            if inputs is not None:
                for tx_input in inputs:
                    input_address = tx_input["address"]
                    transaction = pending_transactions.filter(contract__address=input_address)
                    if transaction.exists():
                        transaction = transaction.first()
                        validate_transaction(txid, transaction.action, transaction.contract.id)
    except Exception:
        pass

def validate_transaction(txid, action, contract_id):
    '''
    Validates if a transaction is valid based on the requirements of its contract.
    '''
    logger.warning(f'RampP2P validating tx: {txid}')

    txn = get_transaction_details(txid)
    handle_transaction_validation.apply_async(
        args=(txn, action, contract_id)
    )

def get_transaction_details(txid):
    response = {
        'valid': False,
        'details': {}
    }

    if txid:
        node = Node()
        txn = node.BCH.get_transaction(txid)

        if txn is None:
            try:
                url = f'https://watchtower.cash/api/transactions/{txid}/' 
                txn = (requests.get(url)).json().get('details')
                logger(f'txn: {txn}')
            except Exception as err:
                logger.warning(f'err: {err.args[0]}')
        
        if txn != None:
            response['valid'] = True
            response['details'] = txn
    
    return response
