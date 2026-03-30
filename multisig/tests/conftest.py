import pytest
from django.test import TestCase
from rest_framework.test import APIClient

from multisig.models.auth import ServerIdentity
from multisig.models.wallet import MultisigWallet, Signer, KeyRecord
from multisig.models.transaction import (
    Proposal,
    Input,
    Psbt,
    Signature,
    Bip32Derivation,
)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def server_identity(db):
    return ServerIdentity.objects.create(
        public_key="02ab" * 16 + "02",  # 66 char hex for compressed pubkey
        message="test_message",
        signature="test_signature",
    )


@pytest.fixture
def another_server_identity(db):
    return ServerIdentity.objects.create(
        public_key="03cd" * 16 + "03",  # 66 char hex for compressed pubkey
        message="another_message",
        signature="another_signature",
    )


@pytest.fixture
def multisig_wallet(db, server_identity):
    return MultisigWallet.objects.create(
        name="Test Multisig Wallet",
        coordinator=server_identity,
        wallet_hash="test_wallet_hash_12345",
        wallet_descriptor_id="test_descriptor_id_12345",
        version=1,
    )


@pytest.fixture
def signer(db, multisig_wallet):
    return Signer.objects.create(
        name="Test Signer",
        master_fingerprint="abc12345",
        derivation_path="m/999'/0'/0'",
        wallet=multisig_wallet,
        auth_public_key="02ab" * 16 + "02",  # 66 char hex
    )


@pytest.fixture
def another_signer(db, multisig_wallet):
    return Signer.objects.create(
        name="Another Signer",
        master_fingerprint="def67890",
        derivation_path="m/999'/0'/0'",
        wallet=multisig_wallet,
        auth_public_key="03cd" * 16 + "03",  # 66 char hex
    )


@pytest.fixture
def key_record(db, server_identity, multisig_wallet):
    return KeyRecord.objects.create(
        publisher=server_identity,
        key_record="encrypted_key_record_data",
        audience_auth_public_key="02ab" * 16 + "02",  # 66 char hex
        wallet=multisig_wallet,
    )


@pytest.fixture
def proposal(db, multisig_wallet, signer):
    return Proposal.objects.create(
        wallet=multisig_wallet,
        coordinator=signer,
        unsigned_transaction_hex="0100000001abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890010000006a4730440220abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef12345678900201abcdexample03",
        proposal="cHNidP8BAFUCAAAAAbCdEfGhIjKlMnOpQrStUvWxYzAbCdEfGhIjKlMnOpQAAAAAAD9kj3C/k8Zq1tVwDqAAAAAAA=",
        proposal_format="psbt",
    )


@pytest.fixture
def input_model(db, proposal):
    return Input.objects.create(
        proposal=proposal,
        outpoint_transaction_hash="abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        outpoint_index=0,
        redeem_script="5221ab" * 33 + "ae",
    )


@pytest.fixture
def psbt_model(db, proposal):
    return Psbt.objects.create(
        proposal=proposal,
        content="cHNidP8BAFUCAAAAAbCdEfGhIjKlMnOpQrStUvWxYzAbCdEfGhIjKlMnOpQAAAAAAD9kj3C/k8Zq1tVwDqAAAAAAA=",
        standard="psbt",
        encoding="base64",
    )


@pytest.fixture
def signature_model(db, input_model, psbt_model):
    return Signature.objects.create(
        input=input_model,
        psbt=psbt_model,
        public_key="02ab" * 16 + "02",  # 66 char hex
        signature="abcedf1234567890" * 8,  # 128 char hex - max is 160
    )


@pytest.fixture
def bip32_derivation_model(db, input_model):
    return Bip32Derivation.objects.create(
        input=input_model,
        path="m/999'/0'/0'/0/0",
        public_key="02ab" * 16 + "02",  # 66 char hex
        master_fingerprint="abc12345",
    )


@pytest.fixture
def mock_js_client(mocker):
    mock_decode = mocker.MagicMock()
    mock_decode.ok = True
    mock_decode.json.return_value = {
        "signingProgress": {"signingProgress": "unsigned"},
        "inputs": [],
        "unsignedTransactionHex": "0100000001abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890010000006a4730440220abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef12345678900201abcdexample03",
        "combinedPsbt": "cHNidP8BAFUCAAAAAbCdEfGhIjKlMnOpQrStUvWxYzAbCdEfGhIjKlMnOpQAAAAAAD9kj3C/k8Zq1tVwDqAAAAAAA=",
    }

    mock_verify = mocker.MagicMock()
    mock_verify.json.return_value = {"success": True}

    mocker.patch("multisig.js_client.decode_psbt", return_value=mock_decode)
    mocker.patch("multisig.js_client.verify_signature", return_value=mock_verify)
    mocker.patch(
        "multisig.serializers.transaction.js_client.decode_psbt",
        return_value=mock_decode,
    )
    mocker.patch(
        "multisig.serializers.transaction.js_client.combine_psbts",
        return_value=mock_verify,
    )

    return {"decode": mock_decode, "verify": mock_verify}
