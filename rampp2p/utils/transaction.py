from rampp2p.tasks.transaction_tasks import handle_transaction_validation
from django.conf import settings
from rampp2p.models import Transaction
from main.utils.queries.node import Node
import requests

import logging
logger = logging.getLogger(__name__)

def process_transaction(txid, output_address, inputs=None):
    logger.warning(f'RampP2P processing tx {txid}')
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
        txn = fetch_txn_from_bchn(txid)

        # Alternative fetching of transaction in debug mode
        if settings.DEBUG:
            if txn is None: 
                txn = fetch_txn_from_watchtower(txid)

        # # Alternative fetching of transaction if bchn returns None
        # if txn is None:
        #     txn = fetch_txn_from_bchjs(txid)
        
        if txn != None:
            response['valid'] = True
            response['details'] = txn
    
    return response
    
def fetch_txn_from_watchtower(txid):
    try:
        url = f'https://watchtower.cash/api/transactions/{txid}/' 
        txn = (requests.get(url)).json().get('details')
        logger.info(f'Fetch txn from watchtower: {txn}')
    except Exception as err:
        logger.warning(f'err: {err.args[0]}')
    return txn

def fetch_txn_from_bchn(txid):
    node = Node()
    txn = node.BCH.get_transaction(txid)
    logger.info(f'Fetch txn from bchn: {txn}')
    return txn

class BCHJS:
    def __init__(self, rest_url, api_token):
        self.rest_url = rest_url
        self.api_token = api_token

    def tx_data(self, txid):
        headers = {'authorization': self.api_token}
        response = requests.get(f'{self.rest_url}electrumx/tx/data/{txid}', headers=headers)
        response.raise_for_status()
        return response.json()
    
def fetch_txn_from_bchjs(txid):
    bchjs = BCHJS(rest_url='https://api.fullstack.cash/v5/', api_token=settings.BCHJS_TOKEN) 
    try: 
        raw_txn = bchjs.tx_data(txid) 
        txn = parse_raw_transaction(bchjs, raw_txn, txid) 
        logger.info(f'Fetch txn from bchjs: {txn}') 
        return txn
    except Exception as error: 
        logger.exception(error)

def parse_raw_transaction(bchjs, txn, txid):
    timestamp = txn['details'].get('time')
    confirmations = txn['details'].get('confirmations')
    vin = txn['details']['vin']
    vout = txn['details']['vout']

    # Inputs
    inputs = []
    for prev_out in vin:
        prev_out_tx = bchjs.tx_data(prev_out['txid'])
        address = prev_out_tx['details']['vout'][prev_out['vout']]['scriptPubKey']['addresses'][0]
        value = prev_out_tx['details']['vout'][prev_out['vout']]['value']
        inputs.append({ "address": address, "value": value })

    # Outputs
    outputs = []
    for out in vout: 
        address = out['scriptPubKey']['addresses'][0] 
        value = out['value'] 
        outputs.append({ "address": address, "value": value })

    results = { 
        "txid": txid, 
        "timestamp": timestamp, 
        "confirmations": confirmations, 
        "inputs": inputs, 
        "outputs": outputs 
    }
    return results