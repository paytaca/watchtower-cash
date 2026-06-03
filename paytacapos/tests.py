from cryptography.fernet import Fernet
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import AuthToken
from main.models import Project, Wallet
from paytacapos.models import Merchant


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

        self.assertEqual(response.status_code, 403)
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