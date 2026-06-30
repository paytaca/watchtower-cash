from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from unittest.mock import patch, MagicMock

from nostr.models import NostrPubkey


VALID_HEX = "aabbccdd0011eeffaabbccdd0011eeffaabbccdd0011eeffaabbccdd0011eeff"
OTHER_HEX = "bbccddee0022ffaabbccddee0022ffaabbccddee0022ffaabbccddee0022ffaa"


class PubkeyLastOnlineViewTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/nostr/last-active/"
        self._setup_auth()

    def _setup_auth(self):
        mock_user = MagicMock()
        mock_user.user_id = "test_user_001"
        mock_user.bitcoincash_address = "bitcoincash:test"
        mock_user.is_anonymous = False
        self.client.force_authenticate(user=mock_user)

    def test_unregistered_pubkey_returns_null(self):
        response = self.client.post(
            self.url,
            {"pubkeys": [VALID_HEX]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[VALID_HEX], None)

    def test_mixed_registered_and_unregistered(self):
        now = timezone.now()
        np = NostrPubkey.objects.create(
            pubkey_hex=VALID_HEX,
            wallet_hash="wh1",
        )
        NostrPubkey.objects.filter(pk=np.pk).update(last_active=now)

        response = self.client.post(
            self.url,
            {"pubkeys": [VALID_HEX, OTHER_HEX]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        expected = now.isoformat().replace("+00:00", "Z")
        self.assertEqual(response.data[VALID_HEX], expected)
        self.assertIsNone(response.data[OTHER_HEX])

    def test_uses_nostrpubkey_last_active(self):
        now = timezone.now()
        np = NostrPubkey.objects.create(
            pubkey_hex=VALID_HEX,
            wallet_hash="wh1",
        )
        NostrPubkey.objects.filter(pk=np.pk).update(last_active=now)

        response = self.client.post(
            self.url,
            {"pubkeys": [VALID_HEX]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        expected = now.isoformat().replace("+00:00", "Z")
        self.assertEqual(response.data[VALID_HEX], expected)

    def test_null_last_active_returns_null(self):
        NostrPubkey.objects.create(
            pubkey_hex=VALID_HEX,
            wallet_hash="wh1",
        )

        response = self.client.post(
            self.url,
            {"pubkeys": [VALID_HEX]},
            content_type="application/json",
        )
        self.assertIsNone(response.data[VALID_HEX])

    def test_response_is_flat_dict(self):
        response = self.client.post(
            self.url,
            {"pubkeys": [VALID_HEX]},
            content_type="application/json",
        )
        self.assertIsInstance(response.data, dict)

    def test_timestamp_is_iso_format(self):
        now = timezone.now()
        np = NostrPubkey.objects.create(
            pubkey_hex=VALID_HEX,
            wallet_hash="wh1",
        )
        NostrPubkey.objects.filter(pk=np.pk).update(last_active=now)

        response = self.client.post(
            self.url,
            {"pubkeys": [VALID_HEX]},
            content_type="application/json",
        )
        ts = response.data[VALID_HEX]
        self.assertIsInstance(ts, str)
        self.assertIn("Z", ts)
        self.assertNotIn("+00:00", ts)

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

    def test_unauthenticated_request_is_rejected(self):
        unauth_client = APIClient()
        response = unauth_client.post(
            self.url,
            {"pubkeys": [VALID_HEX]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
