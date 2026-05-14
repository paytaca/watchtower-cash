from django.test import TestCase

from multisig.serializers.wallet import (
    KeyRecordReadOnlySerializer,
    SignerSerializer,
    MultisigWalletSerializer,
)
from multisig.serializers.transaction import (
    InputSerializer,
    ProposalSerializer,
    PsbtSerializer,
    Bip32DerivationSerializer,
)
from multisig.models.wallet import MultisigWallet, Signer, KeyRecord
from multisig.models.transaction import Proposal, Input, Psbt, Bip32Derivation
from multisig.models.auth import ServerIdentity


class KeyRecordReadOnlySerializerTestCase(TestCase):
    def setUp(self):
        self.identity = ServerIdentity.objects.create(
            public_key="02ab" * 16 + "02", message="test", signature="sig"
        )
        self.wallet = MultisigWallet.objects.create(
            name="Test Wallet", coordinator=self.identity
        )
        self.key_record = KeyRecord.objects.create(
            publisher=self.identity,
            key_record="encrypted_data",
            audience_auth_public_key="02ab" * 16 + "02",
            wallet=self.wallet,
        )

    def test_serialize_key_record(self):
        serializer = KeyRecordReadOnlySerializer(self.key_record)
        data = serializer.data
        self.assertEqual(data["id"], self.key_record.id)
        self.assertEqual(data["key_record"], self.key_record.key_record)


class SignerSerializerTestCase(TestCase):
    def setUp(self):
        self.identity = ServerIdentity.objects.create(
            public_key="02ab" * 16 + "02", message="test", signature="sig"
        )
        self.wallet = MultisigWallet.objects.create(
            name="Test Wallet", coordinator=self.identity
        )
        self.signer = Signer.objects.create(
            name="Test Signer",
            master_fingerprint="abc12345",
            derivation_path="m/999'/0'/0'",
            wallet=self.wallet,
            auth_public_key="02ab" * 16 + "02",
        )

    def test_serialize_signer(self):
        serializer = SignerSerializer(self.signer)
        data = serializer.data
        self.assertEqual(data["id"], self.signer.id)
        self.assertEqual(data["name"], self.signer.name)
        self.assertEqual(data["masterFingerprint"], self.signer.master_fingerprint)


class MultisigWalletSerializerTestCase(TestCase):
    def setUp(self):
        self.identity = ServerIdentity.objects.create(
            public_key="02ab" * 16 + "02", message="test", signature="sig"
        )

    def test_serialize_wallet(self):
        wallet = MultisigWallet.objects.create(
            name="Test Wallet",
            coordinator=self.identity,
            wallet_hash="hash123",
            wallet_descriptor_id="desc123",
        )
        serializer = MultisigWalletSerializer(wallet)
        data = serializer.data
        self.assertEqual(data["id"], wallet.id)
        self.assertEqual(data["name"], wallet.name)


class InputSerializerTestCase(TestCase):
    def setUp(self):
        self.identity = ServerIdentity.objects.create(
            public_key="02ab" * 16 + "02", message="test", signature="sig"
        )
        self.wallet = MultisigWallet.objects.create(
            name="Test Wallet", coordinator=self.identity
        )
        self.signer = Signer.objects.create(
            name="Test Signer",
            master_fingerprint="abc12345",
            derivation_path="m/999'/0'/0'",
            wallet=self.wallet,
            auth_public_key="02ab" * 16 + "02",
        )
        self.proposal = Proposal.objects.create(
            wallet=self.wallet,
            coordinator=self.signer,
            unsigned_transaction_hex="0100000001abcdef1234567890abcdef1234567890010000006a4730440220abcdef1234567890",
            proposal="cHNidP8BAFUCAAAAAbCdEfGhIjKlMnOpQrStUvWxYzAbCdEfGhIjKlMnOpQAAAAAAD9kj3C/k8Zq1tVwDqAAAAAAA=",
            proposal_format="psbt",
        )
        self.input_model = Input.objects.create(
            proposal=self.proposal,
            outpoint_transaction_hash="abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            outpoint_index=0,
        )

    def test_serialize_input(self):
        serializer = InputSerializer(self.input_model)
        data = serializer.data
        self.assertEqual(data["id"], self.input_model.id)
        self.assertEqual(data["outpointIndex"], 0)


class ProposalSerializerTestCase(TestCase):
    def setUp(self):
        self.identity = ServerIdentity.objects.create(
            public_key="02ab" * 16 + "02", message="test", signature="sig"
        )
        self.wallet = MultisigWallet.objects.create(
            name="Test Wallet", coordinator=self.identity
        )
        self.signer = Signer.objects.create(
            name="Test Signer",
            master_fingerprint="abc12345",
            derivation_path="m/999'/0'/0'",
            wallet=self.wallet,
            auth_public_key="02ab" * 16 + "02",
        )
        self.proposal = Proposal.objects.create(
            wallet=self.wallet,
            coordinator=self.signer,
            unsigned_transaction_hex="0100000001abcdef1234567890abcdef1234567890010000006a4730440220abcdef1234567890",
            proposal="cHNidP8BAFUCAAAAAbCdEfGhIjKlMnOpQrStUvWxYzAbCdEfGhIjKlMnOpQAAAAAAD9kj3C/k8Zq1tVwDqAAAAAAA=",
            proposal_format="psbt",
        )

    def test_serialize_proposal(self):
        serializer = ProposalSerializer(self.proposal)
        data = serializer.data
        self.assertEqual(data["id"], self.proposal.id)
        self.assertEqual(data["wallet"], self.proposal.wallet.id)
        self.assertEqual(data["status"], self.proposal.status)


class PsbtSerializerTestCase(TestCase):
    def setUp(self):
        self.identity = ServerIdentity.objects.create(
            public_key="02ab" * 16 + "02", message="test", signature="sig"
        )
        self.wallet = MultisigWallet.objects.create(
            name="Test Wallet", coordinator=self.identity
        )
        self.signer = Signer.objects.create(
            name="Test Signer",
            master_fingerprint="abc12345",
            derivation_path="m/999'/0'/0'",
            wallet=self.wallet,
            auth_public_key="02ab" * 16 + "02",
        )
        self.proposal = Proposal.objects.create(
            wallet=self.wallet,
            coordinator=self.signer,
            unsigned_transaction_hex="0100000001abcdef1234567890abcdef1234567890010000006a4730440220abcdef1234567890",
            proposal="cHNidP8BAFUCAAAAAbCdEfGhIjKlMnOpQrStUvWxYzAbCdEfGhIjKlMnOpQAAAAAAD9kj3C/k8Zq1tVwDqAAAAAAA=",
            proposal_format="psbt",
        )
        self.psbt = Psbt.objects.create(
            proposal=self.proposal,
            content="cHNidP8BAFUCAAAAAbCdEfGhIjKlMnOpQrStUvWxYzAbCdEfGhIjKlMnOpQAAAAAAD9kj3C/k8Zq1tVwDqAAAAAAA=",
            standard="psbt",
            encoding="base64",
        )

    def test_serialize_psbt(self):
        serializer = PsbtSerializer(self.psbt)
        data = serializer.data
        self.assertEqual(data["id"], self.psbt.id)
        self.assertEqual(data["content"], self.psbt.content)
        self.assertIsNotNone(data["contentHash"])


class Bip32DerivationSerializerTestCase(TestCase):
    def setUp(self):
        self.identity = ServerIdentity.objects.create(
            public_key="02ab" * 16 + "02", message="test", signature="sig"
        )
        self.wallet = MultisigWallet.objects.create(
            name="Test Wallet", coordinator=self.identity
        )
        self.signer = Signer.objects.create(
            name="Test Signer",
            master_fingerprint="abc12345",
            derivation_path="m/999'/0'/0'",
            wallet=self.wallet,
            auth_public_key="02ab" * 16 + "02",
        )
        self.proposal = Proposal.objects.create(
            wallet=self.wallet,
            coordinator=self.signer,
            unsigned_transaction_hex="0100000001abcdef1234567890abcdef1234567890010000006a4730440220abcdef1234567890",
            proposal="cHNidP8BAFUCAAAAAbCdEfGhIjKlMnOpQrStUvWxYzAbCdEfGhIjKlMnOpQAAAAAAD9kj3C/k8Zq1tVwDqAAAAAAA=",
            proposal_format="psbt",
        )
        self.input_model = Input.objects.create(
            proposal=self.proposal,
            outpoint_transaction_hash="abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            outpoint_index=0,
        )
        self.derivation = Bip32Derivation.objects.create(
            input=self.input_model,
            path="m/999'/0'/0'/0/0",
            public_key="02ab" * 16 + "02",
            master_fingerprint="abc12345",
        )

    def test_serialize_bip32_derivation(self):
        serializer = Bip32DerivationSerializer(self.derivation)
        data = serializer.data
        self.assertEqual(data["id"], self.derivation.id)
        self.assertEqual(data["path"], self.derivation.path)
        self.assertEqual(data["publicKey"], self.derivation.public_key)
