import json
import pytest
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch, MagicMock

from multisig.models.auth import ServerIdentity
from multisig.models.wallet import MultisigWallet, Signer, KeyRecord
from multisig.models.transaction import (
    Proposal,
    Input,
    Psbt,
    Signature,
    Bip32Derivation,
)


class MultisigWalletViewTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_get_wallet_not_found(self):
        response = self.client.get("/api/multisig/wallets/nonexistent/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class SignerWalletListViewTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_list_wallets_missing_identifier(self):
        response = self.client.get("/api/multisig/signers//wallets/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class KeyRecordViewTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_list_key_records_missing_params(self):
        response = self.client.get("/api/multisig/key-records/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ProposalViewTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
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

    def test_list_proposals(self):
        response = self.client.get("/api/multisig/proposals/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_proposals_filter_by_wallet(self):
        response = self.client.get(f"/api/multisig/proposals/?wallet={self.wallet.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_proposals_filter_by_status(self):
        response = self.client.get("/api/multisig/proposals/?status=pending")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_proposal_by_id(self):
        response = self.client.get(f"/api/multisig/proposals/{self.proposal.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_proposal_by_hash(self):
        response = self.client.get(
            f"/api/multisig/proposals/{self.proposal.unsigned_transaction_hash}/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class WalletProposalListViewTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.identity = ServerIdentity.objects.create(
            public_key="02ab" * 16 + "02", message="test_msg", signature="test_sig"
        )
        self.wallet = MultisigWallet.objects.create(
            name="Test Wallet",
            coordinator=self.identity,
            wallet_hash="test_hash",
            wallet_descriptor_id="test_desc",
        )
        self.proposal = Proposal.objects.create(
            wallet=self.wallet,
            coordinator=Signer.objects.create(
                name="Test Signer",
                master_fingerprint="abc12345",
                derivation_path="m/999'/0'/0'",
                wallet=self.wallet,
                auth_public_key="02ab" * 16 + "02",
            ),
            unsigned_transaction_hex="0100000001abcdef1234567890abcdef1234567890010000006a4730440220abcdef1234567890",
            proposal="cHNidP8BAFUCAAAAAbCdEfGhIjKlMnOpQrStUvWxYzAbCdEfGhIjKlMnOpQAAAAAAD9kj3C/k8Zq1tVwDqAAAAAAA=",
            proposal_format="psbt",
        )

    def test_list_wallet_proposals(self):
        response = self.client.get(f"/api/multisig/wallets/{self.wallet.id}/proposals/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_wallet_proposals_by_hash(self):
        response = self.client.get(
            f"/api/multisig/wallets/{self.wallet.wallet_hash}/proposals/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class ProposalSignatureViewTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
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

    def test_list_signatures(self):
        response = self.client.get(
            f"/api/multisig/proposals/{self.proposal.id}/signatures/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
