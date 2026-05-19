import time
from django.test import TestCase, RequestFactory
from rest_framework.exceptions import AuthenticationFailed

from multisig.auth.auth import (
    parse_x_signature_header,
    parse_signatures,
    normalize_timestamp,
    is_valid_timestamp,
    MultisigStatelessUser,
    PubKeySignatureMessageAuthentication,
)
from multisig.models.auth import ServerIdentity


class ParseXSignatureHeaderTestCase(TestCase):
    def test_parse_schnorr_only(self):
        result = parse_x_signature_header("schnorr=abc123")
        self.assertEqual(result["schnorr"], "abc123")
        self.assertEqual(result["der"], "")

    def test_parse_der_only(self):
        result = parse_x_signature_header("der=def456")
        self.assertEqual(result["schnorr"], "")
        self.assertEqual(result["der"], "def456")

    def test_parse_both(self):
        result = parse_x_signature_header("schnorr=abc123;der=def456")
        self.assertEqual(result["schnorr"], "abc123")
        self.assertEqual(result["der"], "def456")

    def test_parse_empty(self):
        result = parse_x_signature_header("")
        self.assertEqual(result["schnorr"], "")
        self.assertEqual(result["der"], "")

    def test_parse_none(self):
        result = parse_x_signature_header(None)
        self.assertEqual(result["schnorr"], "")
        self.assertEqual(result["der"], "")

    def test_parse_with_spaces(self):
        result = parse_x_signature_header("  schnorr = abc123 ; der = def456  ")
        self.assertEqual(result["schnorr"], "abc123")
        self.assertEqual(result["der"], "def456")


class ParseSignaturesTestCase(TestCase):
    def test_parse_signatures_shorthand(self):
        result = parse_signatures("schnorr=abc123;der=def456")
        self.assertEqual(result["schnorr"], "abc123")
        self.assertEqual(result["der"], "def456")


class NormalizeTimestampTestCase(TestCase):
    def test_normalize_seconds(self):
        ts = 1723489212
        result = normalize_timestamp(ts)
        self.assertEqual(result, ts)

    def test_normalize_milliseconds(self):
        ts = 1723489212000
        result = normalize_timestamp(ts)
        self.assertEqual(result, 1723489212)

    def test_normalize_large_milliseconds(self):
        ts = 1723489212999
        result = normalize_timestamp(ts)
        self.assertEqual(result, 1723489212)

    def test_normalize_invalid_string(self):
        result = normalize_timestamp("not_a_number")
        self.assertIsNone(result)

    def test_normalize_invalid_type(self):
        result = normalize_timestamp(None)
        self.assertIsNone(result)


class IsValidTimestampTestCase(TestCase):
    def test_valid_current_timestamp(self):
        now = int(time.time())
        is_valid, message = is_valid_timestamp(now)
        self.assertTrue(is_valid)
        self.assertEqual(message, "Ok")

    def test_valid_recent_past(self):
        now = int(time.time())
        is_valid, message = is_valid_timestamp(now - 60)
        self.assertTrue(is_valid)

    def test_valid_recent_future(self):
        now = int(time.time())
        is_valid, message = is_valid_timestamp(now + 60)
        self.assertTrue(is_valid)

    def test_invalid_too_old(self):
        now = int(time.time())
        is_valid, message = is_valid_timestamp(now - 300)
        self.assertFalse(is_valid)
        self.assertIn("too old", message)

    def test_invalid_too_future(self):
        now = int(time.time())
        is_valid, message = is_valid_timestamp(now + 300)
        self.assertFalse(is_valid)
        self.assertIn("future", message)


class MultisigStatelessUserTestCase(TestCase):
    def test_user_creation(self):
        user = MultisigStatelessUser()
        self.assertIsNone(user.signer)
        self.assertIsNone(user.wallet)
        self.assertIsNone(user.auth_data)

    def test_user_with_data(self):
        auth_data = {
            "message": "test:123456",
            "public_key": "02ab" * 16 + "02",
            "signature": {"schnorr": "sig123"},
        }
        user = MultisigStatelessUser(auth_data=auth_data)
        self.assertEqual(user.auth_data, auth_data)
        self.assertIsNone(user.signature_verified)

    def test_get_public_key_no_auth_data(self):
        user = MultisigStatelessUser()
        self.assertEqual(user.get_public_key(), "")

    def test_get_public_key_with_auth_data(self):
        auth_data = {
            "message": "test:123456",
            "public_key": "02ab" * 16 + "02",
            "signature": {"schnorr": "sig123"},
        }
        user = MultisigStatelessUser(auth_data=auth_data)
        self.assertEqual(user.get_public_key(), "02ab" * 16 + "02")
