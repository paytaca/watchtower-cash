from django.test import TestCase
from django.utils import timezone
from django.db import IntegrityError

from multisig.models.wallet import MultisigWallet, Signer
from multisig.models.transaction import (
    Proposal,
    Input,
    Psbt,
    Signature,
    Bip32Derivation,
)
from multisig.models.auth import ServerIdentity


class ProposalModelTestCase(TestCase):
    def setUp(self):
        self.identity = ServerIdentity.objects.create(
            public_key="02ab" * 16 + "02", message="test_msg", signature="test_sig"
        )
        self.wallet = MultisigWallet.objects.create(
            name="Test Wallet",
            coordinator=self.identity,
            wallet_hash="test_hash",
            wallet_descriptor_id="test_desc",
        )
        self.signer = Signer.objects.create(
            name="Test Signer",
            master_fingerprint="abc12345",
            derivation_path="m/999'/0'/0'",
            wallet=self.wallet,
            auth_public_key="02ab" * 16 + "02",
        )

    def test_create_proposal(self):
        proposal = Proposal.objects.create(
            wallet=self.wallet,
            coordinator=self.signer,
            unsigned_transaction_hex="0100000001abcdef1234567890abcdef1234567890010000006a4730440220abcdef1234567890",
            proposal="cHNidP8BAFUCAAAAAbCdEfGhIjKlMnOpQrStUvWxYzAbCdEfGhIjKlMnOpQAAAAAAD9kj3C/k8Zq1tVwDqAAAAAAA=",
            proposal_format="psbt",
        )
        self.assertIsNotNone(proposal.id)
        self.assertIsNotNone(proposal.unsigned_transaction_hash)
        self.assertEqual(proposal.status, Proposal.Status.PENDING)

    def test_proposal_soft_delete_pending(self):
        proposal = Proposal.objects.create(
            wallet=self.wallet,
            coordinator=self.signer,
            unsigned_transaction_hex="0100000001abcdef1234567890abcdef1234567890010000006a4730440220abcdef1234567890",
            proposal="psbt_data",
        )
        proposal.soft_delete()
        self.assertIsNotNone(proposal.deleted_at)
        self.assertEqual(proposal.status, Proposal.Status.CANCELLED)

    def test_proposal_statuses(self):
        proposal = Proposal.objects.create(
            wallet=self.wallet,
            coordinator=self.signer,
            unsigned_transaction_hex="0100000001abcdef1234567890abcdef1234567890010000006a4730440220abcdef1234567890",
            proposal="psbt_data",
        )
        for status_choice in [
            Proposal.Status.PENDING,
            Proposal.Status.CANCELLED,
            Proposal.Status.BROADCAST_INITIATED,
            Proposal.Status.BROADCAST_FAILED,
            Proposal.Status.MEMPOOL,
            Proposal.Status.CONFIRMED,
            Proposal.Status.CONFLICTED,
        ]:
            proposal.status = status_choice
            proposal.save()
            self.assertEqual(proposal.status, status_choice)

    def test_proposal_signing_progress_choices(self):
        proposal = Proposal.objects.create(
            wallet=self.wallet,
            coordinator=self.signer,
            unsigned_transaction_hex="0100000001abcdef1234567890abcdef1234567890010000006a4730440220abcdef1234567890",
            proposal="psbt_data",
            signing_progress=Proposal.SigningProgress.UNSIGNED,
        )
        self.assertEqual(proposal.signing_progress, Proposal.SigningProgress.UNSIGNED)
        for progress_choice in [
            Proposal.SigningProgress.UNSIGNED,
            Proposal.SigningProgress.PARTIALLY_SIGNED,
            Proposal.SigningProgress.FULLY_SIGNED,
        ]:
            proposal.signing_progress = progress_choice
            proposal.save()
            self.assertEqual(proposal.signing_progress, progress_choice)


class InputModelTestCase(TestCase):
    def setUp(self):
        self.identity = ServerIdentity.objects.create(
            public_key="02ab" * 16 + "02", message="test_msg", signature="test_sig"
        )
        self.wallet = MultisigWallet.objects.create(
            name="Test Wallet",
            coordinator=self.identity,
            wallet_hash="test_hash",
            wallet_descriptor_id="test_desc",
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

    def test_create_input(self):
        input_model = Input.objects.create(
            proposal=self.proposal,
            outpoint_transaction_hash="abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            outpoint_index=0,
            redeem_script="5221ab" * 33 + "ae",
        )
        self.assertIsNotNone(input_model.id)
        self.assertEqual(input_model.outpoint_index, 0)


class PsbtModelTestCase(TestCase):
    def setUp(self):
        self.identity = ServerIdentity.objects.create(
            public_key="02ab" * 16 + "02", message="test_msg", signature="test_sig"
        )
        self.wallet = MultisigWallet.objects.create(
            name="Test Wallet",
            coordinator=self.identity,
            wallet_hash="test_hash",
            wallet_descriptor_id="test_desc",
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

    def test_create_psbt(self):
        psbt = Psbt.objects.create(
            proposal=self.proposal,
            content="cHNidP8BAFUCAAAAAbCdEfGhIjKlMnOpQrStUvWxYzAbCdEfGhIjKlMnOpQAAAAAAD9kj3C/k8Zq1tVwDqAAAAAAA=",
            standard="psbt",
            encoding="base64",
        )
        self.assertIsNotNone(psbt.id)
        self.assertIsNotNone(psbt.content_hash)

    def test_psbt_compute_content_hash(self):
        content = "cHNidP8BAFUCAAAAAbCdEfGhIjKlMnOpQrStUvWxYzAbCdEfGhIjKlMnOpQAAAAAAD9kj3C/k8Zq1tVwDqAAAAAAA="
        hash1 = Psbt.compute_content_hash(content)
        hash2 = Psbt.compute_content_hash(content)
        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 64)


class SignatureModelTestCase(TestCase):
    def setUp(self):
        self.identity = ServerIdentity.objects.create(
            public_key="02ab" * 16 + "02", message="test_msg", signature="test_sig"
        )
        self.wallet = MultisigWallet.objects.create(
            name="Test Wallet",
            coordinator=self.identity,
            wallet_hash="test_hash",
            wallet_descriptor_id="test_desc",
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
        self.psbt = Psbt.objects.create(
            proposal=self.proposal,
            content="cHNidP8BAFUCAAAAAbCdEfGhIjKlMnOpQrStUvWxYzAbCdEfGhIjKlMnOpQAAAAAAD9kj3C/k8Zq1tVwDqAAAAAAA=",
        )

    def test_create_signature(self):
        signature = Signature.objects.create(
            input=self.input_model,
            psbt=self.psbt,
            public_key="02ab" * 16 + "02",
            signature="abcedf1234567890" * 8,
        )
        self.assertIsNotNone(signature.id)
        self.assertEqual(signature.public_key, "02ab" * 16 + "02")


class Bip32DerivationModelTestCase(TestCase):
    def setUp(self):
        self.identity = ServerIdentity.objects.create(
            public_key="02ab" * 16 + "02", message="test_msg", signature="test_sig"
        )
        self.wallet = MultisigWallet.objects.create(
            name="Test Wallet",
            coordinator=self.identity,
            wallet_hash="test_hash",
            wallet_descriptor_id="test_desc",
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

    def test_create_bip32_derivation(self):
        derivation = Bip32Derivation.objects.create(
            input=self.input_model,
            path="m/999'/0'/0'/0/0",
            public_key="02ab" * 16 + "02",
            master_fingerprint="abc12345",
        )
        self.assertIsNotNone(derivation.id)
        self.assertEqual(derivation.path, "m/999'/0'/0'/0/0")

    def test_bip32_derivation_unique_together(self):
        Bip32Derivation.objects.create(
            input=self.input_model,
            public_key="02ab" * 16 + "02",
            path="m/999'/0'/0'/0/0",
        )
        with self.assertRaises(IntegrityError):
            Bip32Derivation.objects.create(
                input=self.input_model,
                public_key="02ab" * 16 + "02",
                path="m/999'/0'/0'/0/0",
            )
