from django.test import TestCase
from nostr.serializers import (
    PubkeyLastOnlineSerializer,
    MAX_PUBKEYS,
    RoomUpdateSerializer,
)


VALID_HEX = "aabbccdd0011eeffaabbccdd0011eeffaabbccdd0011eeffaabbccdd0011eeff"


class PubkeyLastOnlineSerializerTestCase(TestCase):
    def test_valid_single_pubkey(self):
        serializer = PubkeyLastOnlineSerializer(data={"pubkeys": [VALID_HEX]})
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["pubkeys"], [VALID_HEX])

    def test_valid_multiple_pubkeys(self):
        pubkeys = [f"{i:064x}" for i in range(3)]
        serializer = PubkeyLastOnlineSerializer(data={"pubkeys": pubkeys})
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["pubkeys"], pubkeys)

    def test_pubkeys_lowercased(self):
        upper_hex = VALID_HEX.upper()
        serializer = PubkeyLastOnlineSerializer(data={"pubkeys": [upper_hex]})
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["pubkeys"], [VALID_HEX])

    def test_invalid_hex_string(self):
        serializer = PubkeyLastOnlineSerializer(data={"pubkeys": ["not-hex"]})
        self.assertFalse(serializer.is_valid())

    def test_invalid_length(self):
        short_hex = "abc123"
        serializer = PubkeyLastOnlineSerializer(data={"pubkeys": [short_hex]})
        self.assertFalse(serializer.is_valid())

    def test_empty_list(self):
        serializer = PubkeyLastOnlineSerializer(data={"pubkeys": []})
        self.assertFalse(serializer.is_valid())

    def test_list_exceeds_max_length(self):
        pubkeys = [f"{i:064x}" for i in range(MAX_PUBKEYS + 1)]
        serializer = PubkeyLastOnlineSerializer(data={"pubkeys": pubkeys})
        self.assertFalse(serializer.is_valid())

    def test_mixed_valid_and_invalid(self):
        serializer = PubkeyLastOnlineSerializer(
            data={"pubkeys": [VALID_HEX, "bad"]}
        )
        self.assertFalse(serializer.is_valid())

    def test_missing_field(self):
        serializer = PubkeyLastOnlineSerializer(data={})
        self.assertFalse(serializer.is_valid())


class RoomUpdateSerializerTestCase(TestCase):
    def test_valid_with_members(self):
        serializer = RoomUpdateSerializer(data={
            "wallet_hash": "wh1",
            "members": [VALID_HEX, f"{1:064x}"],
        })
        self.assertTrue(serializer.is_valid())
        self.assertEqual(len(serializer.validated_data["members"]), 2)

    def test_members_optional(self):
        serializer = RoomUpdateSerializer(data={"wallet_hash": "wh1", "name": "x"})
        self.assertTrue(serializer.is_valid())
        self.assertNotIn("members", serializer.validated_data)

    def test_invalid_member_hex(self):
        serializer = RoomUpdateSerializer(data={
            "wallet_hash": "wh1",
            "members": ["not-hex"],
        })
        self.assertFalse(serializer.is_valid())

    def test_member_too_long(self):
        serializer = RoomUpdateSerializer(data={
            "wallet_hash": "wh1",
            "members": ["x" * 65],
        })
        self.assertFalse(serializer.is_valid())


class RoomRolesSerializerTestCase(TestCase):
    def test_owner_is_lowercased(self):
        serializer = RoomUpdateSerializer(data={
            "wallet_hash": "wh1",
            "owner": VALID_HEX.upper(),
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["owner"], VALID_HEX)

    def test_owner_allows_null(self):
        serializer = RoomUpdateSerializer(data={"wallet_hash": "wh1", "owner": None})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertIsNone(serializer.validated_data["owner"])

    def test_owner_must_be_hex(self):
        serializer = RoomUpdateSerializer(data={"wallet_hash": "wh1", "owner": "abc"})
        self.assertFalse(serializer.is_valid())

    def test_admins_are_lowercased_and_deduped(self):
        serializer = RoomUpdateSerializer(data={
            "wallet_hash": "wh1",
            "admins": [VALID_HEX.upper(), VALID_HEX, f"{1:064x}"],
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            serializer.validated_data["admins"], [VALID_HEX, f"{1:064x}"]
        )

    def test_admins_accept_empty_list(self):
        serializer = RoomUpdateSerializer(data={"wallet_hash": "wh1", "admins": []})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["admins"], [])

    def test_admins_reject_null(self):
        """``[]`` is the clear verb; ``null`` must not write SQL NULL into the
        JSON column, which would change its stored shape from list to null."""
        serializer = RoomUpdateSerializer(data={"wallet_hash": "wh1", "admins": None})
        self.assertFalse(serializer.is_valid())

    def test_admins_reject_non_hex_entries(self):
        serializer = RoomUpdateSerializer(data={"wallet_hash": "wh1", "admins": ["nope"]})
        self.assertFalse(serializer.is_valid())

    def test_admins_reject_non_string_entries(self):
        serializer = RoomUpdateSerializer(data={"wallet_hash": "wh1", "admins": [1]})
        self.assertFalse(serializer.is_valid())
