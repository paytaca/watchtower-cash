from rampp2p.tasks.task_transaction import handle_transaction_validation
from django.conf import settings
from rampp2p.models import Transaction
from main.utils.queries.node import Node
import requests

import logging
logger = logging.getLogger(__name__)

def process_transaction(txid, output_address, inputs=None):
    """
    Processes a transaction based on the provided transaction ID and output address.

    This function checks for pending contract transactions with a matching contract address.
    If a matching transaction is found, it is processed as an escrow transaction. If no matching
    transaction is found, it checks the inputs to process it as a refund or release transaction.

    This function is called only when a new main.Transaction is created through main.tasks.save_record().

    Args:
        txid            (str): The transaction ID.
        output_address  (str): The output address of the transaction.
        inputs          (list, optional): A list of input addresses for the transaction. Defaults to None.
    """
    
    logger.warning(f'RampP2P processing tx {txid}')

    try:
        # Find pending contract transactions with contract address = output address
        pending_transactions = Transaction.objects.filter(txid__isnull=True)
        transaction = pending_transactions.filter(contract__address=output_address)

        # If transaction exists, process it as escrow transaction
        if transaction.exists():
            transaction = transaction.first()
            validate_transaction(txid, Transaction.ActionType.ESCROW, transaction.contract.id)
        else:
            # else, process it as refund/release transaction
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
    """
    Entry-point function for validating all P2P exchange contract transactions.

    This function fetches the transaction details and calls the task to perform the 
    necessary validation to determine if a contract transaction is valid for the given action.
    
    Args:
        txid        (str): The transaction ID.
        action_type (str): The validation type to be performed (e.g., 'ESCROW', 'REFUND', 'RELEASE').
        contract_id (int): The ID of the contract associated with the transaction.
    """
    logger.warning(f'RampP2P validating tx: {txid}')

    txn = get_transaction_details(txid)
    handle_transaction_validation.apply_async(
        args=(txn, action, contract_id)
    )

def get_transaction_details(txid):
    """
    Fetches the details of a transaction based on the provided transaction ID.

    This function attempts to fetch the transaction details from the BCH node.
    If the transaction is not found and the application is in debug mode, it
    attempts to fetch the transaction details from the Watchtower service.

    Args:
        txid (str): The transaction ID.

    Returns:
        dict: A dictionary containing the transaction's details.
    """
    response = {
        'valid': False,
        'details': {}
    }

    if txid:
        txn = fetch_txn_from_bchn(txid)

        # Alternative fetching of transaction in debug mode
        if settings.DEBUG:
            if txn is None: 
                txn = fetch_txn_from_watchtower(txid)
        
        if txn != None:
            response['valid'] = True
            response['details'] = txn
    
    return response
    
def fetch_txn_from_watchtower(txid):
    """
    Fetches transaction details from the Watchtower service.

    This function sends a request to the Watchtower service to retrieve the
    details of a transaction based on the provided transaction ID.

    Args:
        txid (str): The transaction ID.

    Returns:
        dict: A dictionary containing the transaction details, or None if not found.
    """
    try:
        url = f'https://watchtower.cash/api/transactions/{txid}/' 
        txn = (requests.get(url)).json().get('details')
        logger.info(f'Fetch txn from watchtower: {txn}')
    except Exception as err:
        logger.warning(f'err: {err.args[0]}')
    return txn

def fetch_txn_from_bchn(txid):
    """
    Fetches transaction details from the BCH node.

    This function uses the Node class to retrieve the details of a transaction
    from the BCH node based on the provided transaction ID.

    Args:
        txid (str): The transaction ID.

    Returns:
        dict: A dictionary containing the transaction details, or None if not found.
    """
    node = Node()
    txn = node.BCH.get_transaction(txid)
    logger.info(f'Fetch txn from bchn: {txn}')
    return txn
