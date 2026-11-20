"""Signing configuration tests that do not import deployment settings or secrets."""
import ast
import importlib.util
from pathlib import Path
import unittest

from django.core import signing
from django.core.exceptions import ImproperlyConfigured


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'signing_secrets_under_test', ROOT / 'watchtower/signing_secrets.py'
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
require_signing_secret = module.require_signing_secret

OLD_TEST_KEY = 'old-synthetic-key-' * 4
NEW_TEST_KEY = 'new-synthetic-key-' * 4


class SigningSecretTests(unittest.TestCase):
    def resolve(self, values):
        """Execute the actual signing assignments without importing other settings."""
        source = ast.parse((ROOT / 'watchtower/settings.py').read_text())
        names = {'SECRET_KEY', 'SIMPLE_JWT', 'LOOKUP_KEY_SECRET'}
        assignments = [
            node for node in source.body if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id in names for t in node.targets)
        ]
        from datetime import timedelta
        namespace = {
            'config': lambda name, default='': values.get(name, default),
            'require_signing_secret': require_signing_secret,
            'timedelta': timedelta,
        }
        exec(compile(ast.Module(body=assignments, type_ignores=[]), '<settings>', 'exec'), namespace)
        return namespace

    def test_both_signing_secrets_are_required(self):
        for values, missing in [({}, 'SECRET_KEY'), ({'SECRET_KEY': NEW_TEST_KEY}, 'JWT_SIGNING_KEY')]:
            with self.subTest(missing=missing), self.assertRaisesRegex(ImproperlyConfigured, missing):
                self.resolve(values)

    def test_rejects_blank_short_and_repetitive_values_without_disclosure(self):
        for value in ['', ' ' * 70, 'too-short', 'a' * 80]:
            with self.subTest(length=len(value)):
                with self.assertRaises(ImproperlyConfigured) as caught:
                    require_signing_secret(lambda *a, **k: value, 'SECRET_KEY')
                if value.strip():
                    self.assertNotIn(value, str(caught.exception))

    def test_rejects_previously_published_key(self):
        # Read from history-free fixture only via a synthetic fingerprint override;
        # the production fingerprint must remain a valid SHA-256 denylist entry.
        import hashlib
        self.assertEqual(len(bytes.fromhex(module._EXPOSED_KEY_SHA256)), 32)
        original = module._EXPOSED_KEY_SHA256
        module._EXPOSED_KEY_SHA256 = hashlib.sha256(OLD_TEST_KEY.encode()).hexdigest()
        try:
            for name in ['SECRET_KEY', 'JWT_SIGNING_KEY']:
                with self.assertRaises(ImproperlyConfigured):
                    require_signing_secret(lambda *a, **k: OLD_TEST_KEY, name)
        finally:
            module._EXPOSED_KEY_SHA256 = original

    def test_independent_keys_and_lookup_secret_are_preserved(self):
        result = self.resolve({
            'SECRET_KEY': NEW_TEST_KEY,
            'JWT_SIGNING_KEY': OLD_TEST_KEY,
            'LOOKUP_KEY_SECRET': 'existing-independent-lookup-key',
        })
        self.assertEqual(result['SECRET_KEY'], NEW_TEST_KEY)
        self.assertEqual(result['SIMPLE_JWT']['SIGNING_KEY'], OLD_TEST_KEY)
        self.assertEqual(result['LOOKUP_KEY_SECRET'], 'existing-independent-lookup-key')

    def test_unset_or_empty_lookup_secret_retains_documented_fallback(self):
        for lookup in [None, '']:
            values = {'SECRET_KEY': NEW_TEST_KEY, 'JWT_SIGNING_KEY': OLD_TEST_KEY}
            if lookup is not None:
                values['LOOKUP_KEY_SECRET'] = lookup
            self.assertEqual(self.resolve(values)['LOOKUP_KEY_SECRET'], NEW_TEST_KEY)

    def test_rotated_secret_rejects_old_signed_data(self):
        old = signing.Signer(key=OLD_TEST_KEY, salt='session-test')
        new = signing.Signer(key=NEW_TEST_KEY, salt='session-test')
        with self.assertRaises(signing.BadSignature):
            new.unsign(old.sign('synthetic-session-data'))
        self.assertEqual(new.unsign(new.sign('synthetic-session-data')), 'synthetic-session-data')


if __name__ == '__main__':
    unittest.main()
