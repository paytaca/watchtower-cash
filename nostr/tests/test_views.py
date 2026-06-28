from django.test import TestCase
from django.utils import timezone
from rest_framework import status

from main.models import Wallet
from nostr.models import NostrPubkey


VALID_HEX = "aabbccdd0011eeffaabbccdd0011eeffaabbccdd0011eeffaabbccdd0011eeff"
OTHER_HEX = "bbccddee0022ffaabbccddee0022ffaabbccddee0022ffaabbccddee0022ffaa"


class PubkeyLastOnlineViewTestCase(TestCase):
    def setUp(self):
        self.url = "/api/nostr/last-online/"

    def test_unregistered_pubkey_returns_null(self):
        response = self.client.post(
            self.url,
            {"pubkeys": [VALID_HEX]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[VALID_HEX], None)

    def test_mixed_registered_and_unregistered(self):
        wallet = Wallet.objects.create(
            wallet_hash="wh1",
            wallet_type="P",
            version=1,
            last_balance_check=timezone.now(),
        )
        NostrPubkey.objects.create(
            pubkey_hex=VALID_HEX,
            wallet_hash=wallet.wallet_hash,
        )

        response = self.client.post(
            self.url,
            {"pubkeys": [VALID_HEX, OTHER_HEX]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data[VALID_HEX])
        self.assertIsNone(response.data[OTHER_HEX])

    def test_uses_nostrpubkey_last_active(self):
        now = timezone.now()
        wallet = Wallet.objects.create(
            wallet_hash="wh1",
            wallet_type="P",
            version=1,
            last_balance_check=None,
        )
        NostrPubkey.objects.create(
            pubkey_hex=VALID_HEX,
            wallet_hash=wallet.wallet_hash,
            last_active=now,
        )

        response = self.client.post(
            self.url,
            {"pubkeys": [VALID_HEX]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        expected = now.isoformat().replace("+00:00", "Z")
        self.assertEqual(response.data[VALID_HEX], expected)

    def test_uses_wallet_last_balance_check(self):
        now = timezone.now()
        wallet = Wallet.objects.create(
            wallet_hash="wh1",
            wallet_type="P",
            version=1,
            last_balance_check=now,
        )
        NostrPubkey.objects.create(
            pubkey_hex=VALID_HEX,
            wallet_hash=wallet.wallet_hash,
            last_active=None,
        )

        response = self.client.post(
            self.url,
            {"pubkeys": [VALID_HEX]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        expected = now.isoformat().replace("+00:00", "Z")
        self.assertEqual(response.data[VALID_HEX], expected)

    def test_returns_max_of_both_timestamps(self):
        earlier = timezone.now() - timezone.timedelta(hours=2)
        later = timezone.now()

        wallet = Wallet.objects.create(
            wallet_hash="wh1",
            wallet_type="P",
            version=1,
            last_balance_check=earlier,
        )
        NostrPubkey.objects.create(
            pubkey_hex=VALID_HEX,
            wallet_hash=wallet.wallet_hash,
            last_active=later,
        )

        response = self.client.post(
            self.url,
            {"pubkeys": [VALID_HEX]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        expected = later.isoformat().replace("+00:00", "Z")
        self.assertEqual(response.data[VALID_HEX], expected)

    def test_response_is_flat_dict(self):
        response = self.client.post(
            self.url,
            {"pubkeys": [VALID_HEX]},
            content_type="application/json",
        )
        self.assertIsInstance(response.data, dict)

    def test_timestamp_is_iso_format(self):
        now = timezone.now()
        wallet = Wallet.objects.create(
            wallet_hash="wh1",
            wallet_type="P",
            version=1,
            last_balance_check=now,
        )
        NostrPubkey.objects.create(
            pubkey_hex=VALID_HEX,
            wallet_hash=wallet.wallet_hash,
        )

        response = self.client.post(
            self.url,
            {"pubkeys": [VALID_HEX]},
            content_type="application/json",
        )
        ts = response.data[VALID_HEX]
        self.assertIsInstance(ts, str)
        self.assertIn("Z", ts)
        self.assertNotIn("+00:00", ts)

    def test_multiple_wallets_same_pubkey(self):
        now = timezone.now()
        earlier = now - timezone.timedelta(hours=1)

        w1 = Wallet.objects.create(
            wallet_hash="wh1",
            wallet_type="P",
            version=1,
            last_balance_check=earlier,
        )
        w2 = Wallet.objects.create(
            wallet_hash="wh2",
            wallet_type="P",
            version=1,
            last_balance_check=now,
        )
        NostrPubkey.objects.create(
            pubkey_hex=VALID_HEX,
            wallet_hash=w1.wallet_hash,
        )
        NostrPubkey.objects.create(
            pubkey_hex=VALID_HEX,
            wallet_hash=w2.wallet_hash,
        )

        response = self.client.post(
            self.url,
            {"pubkeys": [VALID_HEX]},
            content_type="application/json",
        )
        expected = now.isoformat().replace("+00:00", "Z")
        self.assertEqual(response.data[VALID_HEX], expected)

    def test_empty_pubkeys_list_is_rejected(self):
        response = self.client.post(
            self.url,
            {"pubkeys": []},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_pubkey_is_rejected(self):
        response = self.client.post(
            self.url,
            {"pubkeys": ["not-a-valid-hex"]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_body_is_rejected(self):
        response = self.client.post(
            self.url,
            {},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_wallet_without_last_balance_check_returns_null(self):
        wallet = Wallet.objects.create(
            wallet_hash="wh1",
            wallet_type="P",
            version=1,
            last_balance_check=None,
        )
        NostrPubkey.objects.create(
            pubkey_hex=VALID_HEX,
            wallet_hash=wallet.wallet_hash,
            last_active=None,
        )

        response = self.client.post(
            self.url,
            {"pubkeys": [VALID_HEX]},
            content_type="application/json",
        )
        self.assertIsNone(response.data[VALID_HEX])
