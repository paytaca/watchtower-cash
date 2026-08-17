from cryptography.fernet import Fernet
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import AuthToken
from main.models import Project, Wallet
import bitcoin

from paytacapos.models import Merchant, PosDevice, LinkedDeviceInfo, UnlinkDeviceRequest


_TEST_FERNET_KEY = Fernet.generate_key().decode()
_TEST_NFC_SERVER_TOKEN = "test-nfc-server-token"


@override_settings(FERNET_KEY=_TEST_FERNET_KEY, NFC_SERVER_TOKEN=_TEST_NFC_SERVER_TOKEN)
class TestMerchantCardRegistrationView(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.project = Project.objects.create(name="test-project")
        self.wallet = Wallet.objects.create(
            wallet_hash="merchant-wallet-hash",
            wallet_type="bch",
            version=1,
            project=self.project,
        )
        self.merchant = Merchant.objects.create(
            wallet_hash=self.wallet.wallet_hash,
            name="Test Merchant",
        )

        self.card_registration_url = reverse(
            "paytacapos-merchants-card-registration",
            kwargs={"pk": self.merchant.id},
        )
        self.merchant_detail_url = reverse(
            "paytacapos-merchants-detail",
            kwargs={"pk": self.merchant.id},
        )

        self.wallet_token = "wallet-token-value"
        encrypted_token = Fernet(_TEST_FERNET_KEY.encode()).encrypt(self.wallet_token.encode()).decode()
        AuthToken.objects.create(
            wallet_hash=self.wallet.wallet_hash,
            key=encrypted_token,
            key_expires_at=timezone.now() + timezone.timedelta(days=1),
        )

    def test_card_registration_with_valid_nfc_token_updates_nfc_enabled(self):
        response = self.client.patch(
            self.card_registration_url,
            {"nfc_enabled": True},
            format="json",
            HTTP_X_NFC_SERVER_TOKEN=_TEST_NFC_SERVER_TOKEN,
        )

        self.assertEqual(response.status_code, 200)
        self.merchant.refresh_from_db()
        self.assertTrue(self.merchant.nfc_enabled)
        self.assertEqual(response.data["id"], self.merchant.id)
        self.assertEqual(response.data["wallet_hash"], self.merchant.wallet_hash)
        self.assertTrue(response.data["nfc_enabled"])

    def test_card_registration_with_invalid_nfc_token_is_rejected(self):
        response = self.client.patch(
            self.card_registration_url,
            {"nfc_enabled": True},
            format="json",
            HTTP_X_NFC_SERVER_TOKEN="invalid-token",
        )

        self.assertEqual(response.status_code, 401)
        self.merchant.refresh_from_db()
        self.assertFalse(self.merchant.nfc_enabled)

    def test_normal_merchant_patch_cannot_update_nfc_enabled(self):
        response = self.client.patch(
            self.merchant_detail_url,
            {"nfc_enabled": True, "name": "Updated Merchant"},
            format="json",
            HTTP_WALLET_HASH=self.wallet.wallet_hash,
            HTTP_AUTHORIZATION=f"Token {self.wallet_token}",
        )

        self.assertEqual(response.status_code, 200)
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.name, "Updated Merchant")
        self.assertFalse(self.merchant.nfc_enabled)
    
    def test_nfc_enabled_filter_requires_nfc_token(self):
        # without token
        response = self.client.get(reverse("paytacapos-merchants-list"), {"nfc_enabled": "true"})
        self.assertEqual(response.status_code, 403)

        # with valid token
        response = self.client.get(
            reverse("paytacapos-merchants-list"),
            {"nfc_enabled": "true"},
            HTTP_X_NFC_SERVER_TOKEN=_TEST_NFC_SERVER_TOKEN,
        )
        self.assertEqual(response.status_code, 200)


class TestPosDeviceUnlink(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.wallet_hash = "test-wallet-hash"
        self.posid = 1
        self.pos_device = PosDevice.objects.create(
            wallet_hash=self.wallet_hash,
            posid=self.posid,
            nfc_payments_enabled=True,
        )
        self.linked_device = LinkedDeviceInfo.objects.create(
            link_code="test-link-code",
        )
        self.pos_device.linked_device = self.linked_device
        self.pos_device.save()

        privkey = bitcoin.random_key()
        self.verifying_pubkey = bitcoin.privkey_to_pubkey(privkey)
        signature = bitcoin.ecdsa_sign(self.linked_device.link_code, privkey)

        self.unlink_request = UnlinkDeviceRequest.objects.create(
            linked_device_info=self.linked_device,
            signature=signature,
            nonce=123,
        )

        self.unlink_url = reverse(
            "paytacapos-devices-unlink-device",
            kwargs={"wallet_hash_posid": f"{self.wallet_hash}:{self.posid}"},
        )

    def test_unlink_device_resets_nfc_payments_enabled(self):
        response = self.client.post(
            self.unlink_url,
            {"verifying_pubkey": self.verifying_pubkey},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.pos_device.refresh_from_db()
        self.assertFalse(self.pos_device.nfc_payments_enabled)
        self.assertFalse(response.data["nfc_payments_enabled"])
        self.assertIsNone(self.pos_device.linked_device)
