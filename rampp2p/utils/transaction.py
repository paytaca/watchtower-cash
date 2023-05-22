from django.conf import settings
from rampp2p import tasks, utils
from typing import List

import logging
logger = logging.getLogger(__name__)

def validate_transaction(txid: str, **kwargs):
    path = './rampp2p/escrow/src/'
    command = 'node {}transaction.js {}'.format(
        path,
        txid
    )
    return tasks.execute_subprocess.apply_async(
                (command,), 
                link=tasks.verify_tx_out.s(
                    txid=txid,
                    action=kwargs.get('action'),
                    contract_id=kwargs.get('contract_id'),
                    wallet_hashes=kwargs.get('wallet_hashes'),
                )
            )
