import logging
import requests

LOGGER = logging.getLogger(__name__)

MULTISIG_JS_SERVER = 'http://localhost:3004'

def get_transaction_hash(transaction_hex: str):
    return requests.post(
        f'{MULTISIG_JS_SERVER}/multisig/utils/get-transaction-hash',
        data = {'transaction': transaction_hex }, timeout=5
    )
    
def finalize_transaction(multisig_transaction, multisig_wallet):
    return requests.post(
        f'{MULTISIG_JS_SERVER}/multisig/transaction/finalize',
        json={'multisigWallet': multisig_wallet, 'multisigTransaction': multisig_transaction },
        timeout=5
    )

def get_signing_progress(multisig_transaction, multisig_wallet):
    return requests.post(
        f'{MULTISIG_JS_SERVER}/multisig/transaction/get-signing-progress',
        json={'multisigWallet': multisig_wallet, 'multisigTransaction': multisig_transaction },
        timeout=5
    )

def get_wallet_utxos(address):
    return requests.get(
        f'{MULTISIG_JS_SERVER}/multisig/wallet/utxos?address={address}',
        timeout=5
    )
