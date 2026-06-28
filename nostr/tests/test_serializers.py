from django.test import TestCase
from nostr.serializers import PubkeyLastOnlineSerializer, MAX_PUBKEYS


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
