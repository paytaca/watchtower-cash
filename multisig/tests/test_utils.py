from django.test import TestCase

from multisig.utils import (
    get_address_index,
    derive_pubkey_from_xpub,
    create_redeem_script,
    get_locking_bytecode,
    get_locking_script,
    get_multisig_wallet_locking_script,
    group_signatures_by_input,
    is_input_fully_signed,
    is_transaction_fully_signed,
    generate_transaction_hash,
)


class GetAddressIndexTestCase(TestCase):
    def test_get_address_index_from_path(self):
        self.assertEqual(get_address_index("m/999'/0'/0'/0/0"), "0")
        self.assertEqual(get_address_index("m/999'/0'/0'/0/15"), "15")
        self.assertEqual(get_address_index("m/999'/0'/0'/0/123"), "123")

    def test_get_address_index_with_hardened(self):
        self.assertEqual(get_address_index("m/999'/0'/0'/0/0'"), "0")

    def test_get_address_index_non_standard(self):
        self.assertEqual(get_address_index("0"), "0")
        self.assertEqual(get_address_index("15"), "15")


class DerivePubkeyFromXpubTestCase(TestCase):
    def test_derive_pubkey_invalid_xpub(self):
        with self.assertRaises(Exception):
            derive_pubkey_from_xpub("invalid_xpub", "0")


class CreateRedeemScriptTestCase(TestCase):
    def test_create_redeem_script_2_of_3(self):
        pubkeys = ["02ab" * 16 + "02", "03cd" * 16 + "03", "04ef" * 16 + "04"]
        script = create_redeem_script(pubkeys, 2)
        self.assertIsNotNone(script)
        self.assertTrue(script.startswith("52"))

    def test_create_redeem_script_3_of_5(self):
        pubkeys = [
            "02ab" * 16 + "02",
            "03cd" * 16 + "03",
            "04ef" * 16 + "04",
            "05gh" * 16 + "05",
            "06ij" * 16 + "06",
        ]
        script = create_redeem_script(pubkeys, 3)
        self.assertIsNotNone(script)
        self.assertTrue(script.startswith("53"))

    def test_create_redeem_script_format(self):
        pubkeys = ["02ab" * 16 + "02", "03cd" * 16 + "03"]
        script = create_redeem_script(pubkeys, 2)
        self.assertIn("52", script)
        self.assertTrue(script.endswith("ae"))


class GetLockingBytecodeTestCase(TestCase):
    def test_get_locking_bytecode(self):
        redeem_script = "5221ab" * 33 + "ae"
        bytecode = get_locking_bytecode(redeem_script)
        self.assertIsNotNone(bytecode)
        self.assertEqual(len(bytecode), 40)

    def test_get_locking_bytecode_empty(self):
        bytecode = get_locking_bytecode("")
        self.assertIsNotNone(bytecode)


class GetLockingScriptTestCase(TestCase):
    def test_get_locking_script(self):
        locking_bytecode = "abcdef12" * 20
        script = get_locking_script(locking_bytecode)
        self.assertIsNotNone(script)
        self.assertTrue(script.startswith("a9"))
        self.assertTrue(script.endswith("87"))


class GroupSignaturesByInputTestCase(TestCase):
    def test_group_signatures_empty(self):
        result = group_signatures_by_input([])
        self.assertEqual(result, {})

    def test_group_signatures_single_input(self):
        signatures = [
            {"inputIndex": 0, "signer": "signer1"},
            {"inputIndex": 0, "signer": "signer2"},
        ]
        result = group_signatures_by_input(signatures)
        self.assertIn(0, result)
        self.assertEqual(len(result[0]), 2)

    def test_group_signatures_multiple_inputs(self):
        signatures = [
            {"inputIndex": 0, "signer": "signer1"},
            {"inputIndex": 1, "signer": "signer2"},
            {"inputIndex": 0, "signer": "signer3"},
        ]
        result = group_signatures_by_input(signatures)
        self.assertEqual(len(result[0]), 2)
        self.assertEqual(len(result[1]), 1)


class IsInputFullySignedTestCase(TestCase):
    def test_input_fully_signed(self):
        grouped = {0: {"signer1", "signer2"}}
        self.assertTrue(is_input_fully_signed(0, grouped, 2))

    def test_input_not_fully_signed(self):
        grouped = {0: {"signer1"}}
        self.assertFalse(is_input_fully_signed(0, grouped, 2))

    def test_input_missing(self):
        grouped = {}
        self.assertFalse(is_input_fully_signed(0, grouped, 2))


class IsTransactionFullySignedTestCase(TestCase):
    def test_transaction_fully_signed(self):
        signatures = [
            {"inputIndex": 0, "signer": "signer1"},
            {"inputIndex": 0, "signer": "signer2"},
            {"inputIndex": 1, "signer": "signer1"},
            {"inputIndex": 1, "signer": "signer2"},
        ]
        required_signatures = {0: 2, 1: 2}
        self.assertTrue(is_transaction_fully_signed(signatures, required_signatures))

    def test_transaction_not_fully_signed(self):
        signatures = [{"inputIndex": 0, "signer": "signer1"}]
        required_signatures = {0: 2}
        self.assertFalse(is_transaction_fully_signed(signatures, required_signatures))


class GenerateTransactionHashTestCase(TestCase):
    def test_generate_transaction_hash_empty(self):
        tx_hex = ""
        result = generate_transaction_hash(tx_hex)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 64)

    def test_generate_transaction_hash_known_value(self):
        tx_hex = "01000000010000000000000000000000000000000000000000000000000000000000000000ffffffff4d04ffff001d0104455468652054696d65732030332f4a616e2f3230313920546865204c696e6520436f696e01000f42454c4c53414e5101000000ffffffff0100f2052a01000000434104d8c449710c0e5476e6f1e252e74d7c5e0ac3e9e45c6c5c2a9c8e0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        result = generate_transaction_hash(tx_hex)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 64)

    def test_generate_transaction_hash_deterministic(self):
        tx_hex = (
            "01000000010000000000000000000000000000000000000000000000000000000000000000"
        )
        hash1 = generate_transaction_hash(tx_hex)
        hash2 = generate_transaction_hash(tx_hex)
        self.assertEqual(hash1, hash2)

    def test_generate_transaction_hash_different_inputs(self):
        hash1 = generate_transaction_hash("0100000001")
        hash2 = generate_transaction_hash("0100000002")
        self.assertNotEqual(hash1, hash2)
