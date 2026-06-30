from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from unittest.mock import patch, MagicMock

from nostr.models import NostrPubkey, NostrRoom, NostrBlockedContact, NostrBlockedGroup


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

    def test_show_active_status_false_returns_null(self):
        now = timezone.now()
        np = NostrPubkey.objects.create(
            pubkey_hex=VALID_HEX,
            wallet_hash="wh1",
            show_active_status=False,
        )
        NostrPubkey.objects.filter(pk=np.pk).update(last_active=now)

        response = self.client.post(
            self.url,
            {"pubkeys": [VALID_HEX]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data[VALID_HEX])

    def test_show_active_status_true_returns_timestamp(self):
        now = timezone.now()
        np = NostrPubkey.objects.create(
            pubkey_hex=VALID_HEX,
            wallet_hash="wh1",
            show_active_status=True,
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

    def test_mixed_show_active_status(self):
        now = timezone.now()
        np_true = NostrPubkey.objects.create(
            pubkey_hex=VALID_HEX,
            wallet_hash="wh1",
            show_active_status=True,
        )
        NostrPubkey.objects.filter(pk=np_true.pk).update(last_active=now)
        np_false = NostrPubkey.objects.create(
            pubkey_hex=OTHER_HEX,
            wallet_hash="wh2",
            show_active_status=False,
        )
        NostrPubkey.objects.filter(pk=np_false.pk).update(last_active=now)

        response = self.client.post(
            self.url,
            {"pubkeys": [VALID_HEX, OTHER_HEX]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        expected = now.isoformat().replace("+00:00", "Z")
        self.assertEqual(response.data[VALID_HEX], expected)
        self.assertIsNone(response.data[OTHER_HEX])

    @patch("nostr.views.Address.objects.filter")
    def test_requester_blocked_returns_all_null(self, mock_addr_filter):
        """When the requester has show_active_status=False on any of their
        wallets, all results must be null."""
        now = timezone.now()
        np = NostrPubkey.objects.create(
            pubkey_hex=VALID_HEX,
            wallet_hash="wh1",
            show_active_status=True,
        )
        NostrPubkey.objects.filter(pk=np.pk).update(last_active=now)

        # Simulate Address lookup finding a wallet whose NostrPubkey
        # has show_active_status=False.
        mock_addr_filter.return_value.values_list.return_value = ["wh_requester_blocked"]
        NostrPubkey.objects.create(
            pubkey_hex="aa" * 32,
            wallet_hash="wh_requester_blocked",
            show_active_status=False,
        )

        response = self.client.post(
            self.url,
            {"pubkeys": [VALID_HEX]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data[VALID_HEX])


class ShowActiveStatusViewTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/nostr/active-status/"
        self.wallet_hash = "wh_test"
        self.nostr_pubkey = NostrPubkey.objects.create(
            pubkey_hex=VALID_HEX,
            wallet_hash=self.wallet_hash,
        )
        self._setup_auth()

    def _setup_auth(self):
        mock_user = MagicMock()
        mock_user.user_id = "test_user_001"
        mock_user.bitcoincash_address = "bitcoincash:test"
        mock_user.is_anonymous = False
        self.client.force_authenticate(user=mock_user)

    @patch("nostr.views.verify_wallet_ownership")
    def test_toggle_on(self, mock_verify):
        mock_verify.return_value = (True, None)

        response = self.client.post(
            self.url,
            {"wallet_hash": self.wallet_hash, "show_active_status": True},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "updated")
        self.assertTrue(response.data["show_active_status"])

        self.nostr_pubkey.refresh_from_db()
        self.assertTrue(self.nostr_pubkey.show_active_status)

    @patch("nostr.views.verify_wallet_ownership")
    def test_toggle_off(self, mock_verify):
        mock_verify.return_value = (True, None)

        self.nostr_pubkey.show_active_status = True
        self.nostr_pubkey.save()

        response = self.client.post(
            self.url,
            {"wallet_hash": self.wallet_hash, "show_active_status": False},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "updated")
        self.assertFalse(response.data["show_active_status"])

        self.nostr_pubkey.refresh_from_db()
        self.assertFalse(self.nostr_pubkey.show_active_status)

    @patch("nostr.views.verify_wallet_ownership")
    def test_wallet_ownership_fails(self, mock_verify):
        mock_verify.return_value = (False, "Wallet does not belong to user")

        response = self.client.post(
            self.url,
            {"wallet_hash": self.wallet_hash, "show_active_status": True},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_request_is_rejected(self):
        unauth_client = APIClient()
        response = unauth_client.post(
            self.url,
            {"wallet_hash": self.wallet_hash, "show_active_status": True},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_missing_wallet_hash_is_rejected(self):
        response = self.client.post(
            self.url,
            {"show_active_status": True},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_show_active_status_is_rejected(self):
        response = self.client.post(
            self.url,
            {"wallet_hash": self.wallet_hash},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class NostrRoomListViewTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/nostr/rooms/"
        self.wallet_hash = "wh_rooms_test"
        self.room_id = "room_abc123"
        self.other_room_id = "room_def456"
        self.room = NostrRoom.objects.create(
            room_id=self.room_id,
            wallet_hash=self.wallet_hash,
            type="private",
            name="Test Room",
            members=[VALID_HEX],
            subject="Hello",
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )
        self._setup_auth()

    def _setup_auth(self):
        mock_user = MagicMock()
        mock_user.user_id = "test_user_001"
        mock_user.bitcoincash_address = "bitcoincash:test"
        mock_user.is_anonymous = False
        self.client.force_authenticate(user=mock_user)

    @patch("nostr.views.verify_wallet_ownership")
    def test_list_rooms(self, mock_verify):
        mock_verify.return_value = (True, None)
        NostrRoom.objects.create(
            room_id=self.other_room_id,
            wallet_hash=self.wallet_hash,
            type="group",
            name="Other Room",
            members=[VALID_HEX, OTHER_HEX],
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )

        response = self.client.get(self.url, {"wallet_hash": self.wallet_hash})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["rooms"]), 2)

    def test_list_rooms_missing_wallet_hash(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("nostr.views.verify_wallet_ownership")
    def test_list_rooms_ownership_fails(self, mock_verify):
        mock_verify.return_value = (False, "Wallet does not belong to user")
        response = self.client.get(self.url, {"wallet_hash": self.wallet_hash})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("nostr.views.verify_wallet_ownership")
    def test_create_room(self, mock_verify):
        mock_verify.return_value = (True, None)
        now = timezone.now()
        response = self.client.post(self.url, {
            "wallet_hash": self.wallet_hash,
            "room": {
                "room_id": "new_room",
                "type": "private",
                "name": "New Room",
                "members": [VALID_HEX],
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            },
        }, content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            NostrRoom.objects.filter(
                wallet_hash=self.wallet_hash, room_id="new_room"
            ).exists()
        )

    def test_create_room_unauthenticated(self):
        unauth_client = APIClient()
        response = unauth_client.post(self.url, {}, content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class NostrRoomDetailViewTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.wallet_hash = "wh_detail_test"
        self.room_id = "room_detail_123"
        self.room = NostrRoom.objects.create(
            room_id=self.room_id,
            wallet_hash=self.wallet_hash,
            type="private",
            name="Detail Room",
            members=[VALID_HEX],
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )
        self.url = f"/api/nostr/rooms/{self.room_id}/"
        self._setup_auth()

    def _setup_auth(self):
        mock_user = MagicMock()
        mock_user.user_id = "test_user_001"
        mock_user.bitcoincash_address = "bitcoincash:test"
        mock_user.is_anonymous = False
        self.client.force_authenticate(user=mock_user)

    @patch("nostr.views.verify_wallet_ownership")
    def test_update_room_name(self, mock_verify):
        mock_verify.return_value = (True, None)
        response = self.client.patch(self.url, {
            "wallet_hash": self.wallet_hash,
            "name": "Updated Name",
        }, content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.room.refresh_from_db()
        self.assertEqual(self.room.name, "Updated Name")

    @patch("nostr.views.verify_wallet_ownership")
    def test_update_room_archived(self, mock_verify):
        mock_verify.return_value = (True, None)
        response = self.client.patch(self.url, {
            "wallet_hash": self.wallet_hash,
            "archived": True,
        }, content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.room.refresh_from_db()
        self.assertTrue(self.room.archived)

    @patch("nostr.views.verify_wallet_ownership")
    def test_delete_room(self, mock_verify):
        mock_verify.return_value = (True, None)
        response = self.client.delete(self.url, {
            "wallet_hash": self.wallet_hash,
        }, content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(
            NostrRoom.objects.filter(room_id=self.room_id).exists()
        )

    @patch("nostr.views.verify_wallet_ownership")
    def test_delete_room_not_found(self, mock_verify):
        mock_verify.return_value = (True, None)
        url = "/api/nostr/rooms/nonexistent/"
        response = self.client.delete(url, {
            "wallet_hash": self.wallet_hash,
        }, content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class NostrRoomBatchSyncViewTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/nostr/rooms/batch-sync/"
        self.wallet_hash = "wh_batch_test"
        self._setup_auth()

    def _setup_auth(self):
        mock_user = MagicMock()
        mock_user.user_id = "test_user_001"
        mock_user.bitcoincash_address = "bitcoincash:test"
        mock_user.is_anonymous = False
        self.client.force_authenticate(user=mock_user)

    @patch("nostr.views.verify_wallet_ownership")
    def test_batch_sync(self, mock_verify):
        mock_verify.return_value = (True, None)
        now = timezone.now()
        rooms_data = [
            {
                "room_id": "batch_room_1",
                "type": "private",
                "name": "Batch One",
                "members": [VALID_HEX],
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            },
            {
                "room_id": "batch_room_2",
                "type": "group",
                "name": "Batch Two",
                "members": [VALID_HEX, OTHER_HEX],
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            },
        ]
        response = self.client.post(self.url, {
            "wallet_hash": self.wallet_hash,
            "rooms": rooms_data,
        }, content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["rooms"]), 2)
        self.assertEqual(
            NostrRoom.objects.filter(wallet_hash=self.wallet_hash).count(), 2
        )


class NostrRoomTouchViewTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.wallet_hash = "wh_touch_test"
        self.room_id = "room_touch_123"
        self.room = NostrRoom.objects.create(
            room_id=self.room_id,
            wallet_hash=self.wallet_hash,
            type="private",
            name="Touch Room",
            members=[VALID_HEX],
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )
        self.url = f"/api/nostr/rooms/{self.room_id}/touch/"
        self._setup_auth()

    def _setup_auth(self):
        mock_user = MagicMock()
        mock_user.user_id = "test_user_001"
        mock_user.bitcoincash_address = "bitcoincash:test"
        mock_user.is_anonymous = False
        self.client.force_authenticate(user=mock_user)

    @patch("nostr.views.verify_wallet_ownership")
    def test_touch_with_timestamp(self, mock_verify):
        mock_verify.return_value = (True, None)
        ts = timezone.now()
        response = self.client.post(self.url, {
            "wallet_hash": self.wallet_hash,
            "timestamp": ts.isoformat(),
        }, content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.room.refresh_from_db()
        self.assertIsNotNone(self.room.last_message_timestamp)

    @patch("nostr.views.verify_wallet_ownership")
    def test_touch_without_timestamp(self, mock_verify):
        mock_verify.return_value = (True, None)
        response = self.client.post(self.url, {
            "wallet_hash": self.wallet_hash,
        }, content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.room.refresh_from_db()
        self.assertIsNotNone(self.room.last_message_timestamp)

    @patch("nostr.views.verify_wallet_ownership")
    def test_touch_room_not_found(self, mock_verify):
        mock_verify.return_value = (True, None)
        url = "/api/nostr/rooms/nonexistent/touch/"
        response = self.client.post(url, {
            "wallet_hash": self.wallet_hash,
        }, content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class NostrBlockListViewTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/nostr/blocks/"
        self.wallet_hash = "wh_blocks_test"
        NostrBlockedContact.objects.create(
            wallet_hash=self.wallet_hash, pub_key_hex=VALID_HEX,
        )
        NostrBlockedGroup.objects.create(
            wallet_hash=self.wallet_hash, room_id="blocked_room_1",
        )
        self._setup_auth()

    def _setup_auth(self):
        mock_user = MagicMock()
        mock_user.user_id = "test_user_001"
        mock_user.bitcoincash_address = "bitcoincash:test"
        mock_user.is_anonymous = False
        self.client.force_authenticate(user=mock_user)

    @patch("nostr.views.verify_wallet_ownership")
    def test_list_blocks(self, mock_verify):
        mock_verify.return_value = (True, None)
        response = self.client.get(self.url, {"wallet_hash": self.wallet_hash})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(VALID_HEX, response.data["blocked_contacts"])
        self.assertIn("blocked_room_1", response.data["blocked_groups"])

    def test_list_blocks_missing_wallet_hash(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class NostrBlockContactViewTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/nostr/blocks/contacts/"
        self.wallet_hash = "wh_block_contact_test"
        self._setup_auth()

    def _setup_auth(self):
        mock_user = MagicMock()
        mock_user.user_id = "test_user_001"
        mock_user.bitcoincash_address = "bitcoincash:test"
        mock_user.is_anonymous = False
        self.client.force_authenticate(user=mock_user)

    @patch("nostr.views.verify_wallet_ownership")
    def test_block_contact(self, mock_verify):
        mock_verify.return_value = (True, None)
        response = self.client.post(self.url, {
            "wallet_hash": self.wallet_hash,
            "pub_key_hex": VALID_HEX,
        }, content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            NostrBlockedContact.objects.filter(
                wallet_hash=self.wallet_hash, pub_key_hex=VALID_HEX,
            ).exists()
        )

    @patch("nostr.views.verify_wallet_ownership")
    def test_unblock_contact(self, mock_verify):
        mock_verify.return_value = (True, None)
        NostrBlockedContact.objects.create(
            wallet_hash=self.wallet_hash, pub_key_hex=VALID_HEX,
        )
        url = f"/api/nostr/blocks/contacts/{VALID_HEX}/"
        response = self.client.delete(url, {
            "wallet_hash": self.wallet_hash,
        }, content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(
            NostrBlockedContact.objects.filter(
                wallet_hash=self.wallet_hash, pub_key_hex=VALID_HEX,
            ).exists()
        )

    @patch("nostr.views.verify_wallet_ownership")
    def test_unblock_contact_not_found(self, mock_verify):
        mock_verify.return_value = (True, None)
        url = f"/api/nostr/blocks/contacts/{VALID_HEX}/"
        response = self.client.delete(url, {
            "wallet_hash": self.wallet_hash,
        }, content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class NostrBlockGroupViewTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/nostr/blocks/groups/"
        self.wallet_hash = "wh_block_group_test"
        self._setup_auth()

    def _setup_auth(self):
        mock_user = MagicMock()
        mock_user.user_id = "test_user_001"
        mock_user.bitcoincash_address = "bitcoincash:test"
        mock_user.is_anonymous = False
        self.client.force_authenticate(user=mock_user)

    @patch("nostr.views.verify_wallet_ownership")
    def test_block_group(self, mock_verify):
        mock_verify.return_value = (True, None)
        response = self.client.post(self.url, {
            "wallet_hash": self.wallet_hash,
            "room_id": "group_123",
        }, content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            NostrBlockedGroup.objects.filter(
                wallet_hash=self.wallet_hash, room_id="group_123",
            ).exists()
        )

    @patch("nostr.views.verify_wallet_ownership")
    def test_unblock_group(self, mock_verify):
        mock_verify.return_value = (True, None)
        NostrBlockedGroup.objects.create(
            wallet_hash=self.wallet_hash, room_id="group_123",
        )
        url = "/api/nostr/blocks/groups/group_123/"
        response = self.client.delete(url, {
            "wallet_hash": self.wallet_hash,
        }, content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(
            NostrBlockedGroup.objects.filter(
                wallet_hash=self.wallet_hash, room_id="group_123",
            ).exists()
        )
