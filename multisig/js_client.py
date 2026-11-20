import logging
from internal_services.client import service_request
from django.core.exceptions import ImproperlyConfigured
from django.conf import settings

LOGGER = logging.getLogger(__name__)

MULTISIG_JS_SERVER = getattr(settings, "MULTISIG", {}).get(
    "JS_SERVER", "http://localhost:3004"
)


def _request(method, path, **kwargs):
    if MULTISIG_JS_SERVER.rstrip('/') not in ('http://localhost:3004', 'http://127.0.0.1:3004'):
        raise ImproperlyConfigured('MULTISIG_JS_SERVER must use loopback port 3004')
    return service_request('multisig', method, path, **kwargs)


def get_transaction_hash(transaction_hex: str):
    return _request(
        'POST',
        "/multisig/utils/get-transaction-hash",
        data={"transaction": transaction_hex},
        timeout=20,
    )


def get_unsigned_transaction_hash(transaction_hex: str):
    return _request(
        'GET',
        f"/multisig/transaction/unsigned-transaction-hash?transaction_hex={transaction_hex}",
        timeout=20,
    )


def finalize_transaction(multisig_transaction, multisig_wallet):
    return _request(
        'POST',
        "/multisig/transaction/finalize",
        json={
            "multisigWallet": multisig_wallet,
            "multisigTransaction": multisig_transaction,
        },
        timeout=20,
    )


def get_signing_progress(multisig_transaction, multisig_wallet):
    return _request(
        'POST',
        "/multisig/transaction/get-signing-progress",
        json={
            "multisigWallet": multisig_wallet,
            "multisigTransaction": multisig_transaction,
        },
        timeout=20,
    )


def get_wallet_utxos(address):
    return _request(
        'GET',
        f"/multisig/wallet/utxos?address={address}", timeout=20
    )


def verify_signature(
    message: str, public_key: str, signature: dict, encoding: str = "utf8"
):
    return _request(
        'POST',
        "/multisig/message/verify-signature",
        json={
            "message": message,
            "publicKey": public_key,
            "signature": signature,
            "encoding": encoding,
        },
        timeout=20,
    )


def decode_proposal(proposal: str, proposal_format: str):
    return _request(
        'POST',
        "/multisig/transaction/decode-proposal",
        json={"proposal": proposal, "proposal_format": proposal_format},
        timeout=20,
    )


def decode_psbt(psbt: str):
    return _request(
        'POST',
        "/multisig/transaction/decode-psbt",
        json={"psbt": psbt},
        timeout=20,
    )


def combine_psbts(psbts: list):
    return _request(
        'POST',
        "/multisig/transaction/combine-psbts",
        json={"psbts": psbts},
        timeout=20,
    )
