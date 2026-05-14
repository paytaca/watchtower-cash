from django.test import TestCase
from django.utils import timezone
from django.db import IntegrityError

from multisig.models.auth import ServerIdentity
from multisig.models.wallet import MultisigWallet, Signer, KeyRecord


class ServerIdentityModelTestCase(TestCase):
    def test_create_server_identity(self):
        identity = ServerIdentity.objects.create(
            public_key="02ab" * 16 + "02",
            message="test_message",
            signature="test_signature",
        )
        self.assertIsNotNone(identity.id)
        self.assertEqual(identity.public_key, "02ab" * 16 + "02")

    def test_server_identity_unique_public_key(self):
        ServerIdentity.objects.create(public_key="02ab" * 16 + "02")
        with self.assertRaises(IntegrityError):
            ServerIdentity.objects.create(public_key="02ab" * 16 + "02")

    def test_server_identity_soft_delete(self):
        identity = ServerIdentity.objects.create(public_key="03cd" * 16 + "03")
        identity.deleted_at = timezone.now()
        identity.save()
        self.assertIsNotNone(identity.deleted_at)


class MultisigWalletModelTestCase(TestCase):
    def test_create_multisig_wallet(self):
        identity = ServerIdentity.objects.create(
            public_key="02ab" * 16 + "02", message="test", signature="sig"
        )
        wallet = MultisigWallet.objects.create(
            name="Test Wallet",
            coordinator=identity,
            wallet_hash="hash123",
            wallet_descriptor_id="desc123",
            version=1,
        )
        self.assertIsNotNone(wallet.id)
        self.assertEqual(wallet.name, "Test Wallet")

    def test_multisig_wallet_soft_delete(self):
        identity = ServerIdentity.objects.create(
            public_key="02ab" * 16 + "02", message="test", signature="sig"
        )
        wallet = MultisigWallet.objects.create(name="To Delete", coordinator=identity)
        wallet.soft_delete()
        self.assertIsNotNone(wallet.deleted_at)

    def test_multisig_wallet_unique_coordinator_descriptor(self):
        identity = ServerIdentity.objects.create(
            public_key="02ab" * 16 + "02", message="test", signature="sig"
        )
        MultisigWallet.objects.create(
            coordinator=identity, wallet_descriptor_id="unique_desc_123"
        )
        with self.assertRaises(IntegrityError):
            MultisigWallet.objects.create(
                coordinator=identity, wallet_descriptor_id="unique_desc_123"
            )


class SignerModelTestCase(TestCase):
    def test_create_signer(self):
        identity = ServerIdentity.objects.create(
            public_key="02ab" * 16 + "02", message="test", signature="sig"
        )
        wallet = MultisigWallet.objects.create(name="Test Wallet", coordinator=identity)
        signer = Signer.objects.create(
            name="Test Signer",
            master_fingerprint="abc12345",
            derivation_path="m/999'/0'/0'",
            wallet=wallet,
            auth_public_key="02ab" * 16 + "02",
        )
        self.assertIsNotNone(signer.id)
        self.assertEqual(signer.name, "Test Signer")

    def test_signer_unique_per_wallet(self):
        identity = ServerIdentity.objects.create(
            public_key="02ab" * 16 + "02", message="test", signature="sig"
        )
        wallet = MultisigWallet.objects.create(name="Test Wallet", coordinator=identity)
        signer = Signer.objects.create(
            name="Test Signer", wallet=wallet, auth_public_key="02ab" * 16 + "02"
        )
        with self.assertRaises(IntegrityError):
            Signer.objects.create(wallet=wallet, auth_public_key=signer.auth_public_key)


class KeyRecordModelTestCase(TestCase):
    def test_create_key_record(self):
        identity = ServerIdentity.objects.create(
            public_key="02ab" * 16 + "02", message="test", signature="sig"
        )
        wallet = MultisigWallet.objects.create(name="Test Wallet", coordinator=identity)
        key_record = KeyRecord.objects.create(
            publisher=identity,
            key_record="encrypted_data",
            audience_auth_public_key="02ab" * 16 + "02",
            wallet=wallet,
        )
        self.assertIsNotNone(key_record.id)
        self.assertEqual(key_record.key_record, "encrypted_data")
