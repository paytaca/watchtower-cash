import hashlib
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import ecdsa

from authentication.backends import SignatureBackend


class SignatureBackendTests(TestCase):
    def setUp(self):
        self.account_key = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)
        self.attacker_key = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)

    def authenticate(self, app, signer=None, public_key=None,
                     registered_key=None, expired=False, nonce='123456',
                     signature=None):
        signer = signer or self.account_key
        self.wallet = SimpleNamespace(
            wallet_hash='synthetic-wallet',
            public_key=registered_key if registered_key is not None else
            self.account_key.get_verifying_key().to_string('compressed').hex(),
        )
        self.token = SimpleNamespace(
            nonce=nonce,
            nonce_expires_at=object(),
            is_nonce_expired=Mock(return_value=expired),
            save=Mock(),
        )
        if public_key is None:
            public_key = signer.get_verifying_key().to_string('compressed').hex()
        if signature is None:
            signature = signer.sign(
                (nonce or '').encode(), hashfunc=hashlib.sha256,
                sigencode=ecdsa.util.sigencode_der,
            ).hex()

        with patch('authentication.backends.PeerWallet.objects.get', return_value=self.wallet), \
             patch('authentication.backends.ArbiterWallet.objects.get', return_value=self.wallet), \
             patch('authentication.backends.AuthToken.objects.get', return_value=self.token):
            return SignatureBackend().authenticate(
                app=app, wallet_hash=self.wallet.wallet_hash,
                public_key=public_key, signature=signature,
            )

    def assert_rejected(self, result):
        self.assertIsNone(result[0])
        self.assertIsNone(result[1])
        self.assertTrue(result[2])
        self.token.save.assert_not_called()

    def test_attacker_key_cannot_authenticate_as_peer_or_arbiter(self):
        for app in ('ramp-peer', 'ramp-arbiter'):
            with self.subTest(app=app):
                self.assert_rejected(self.authenticate(app, signer=self.attacker_key))
                self.assertEqual(self.token.nonce, '123456')

    def test_registered_key_authenticates_and_consumes_nonce(self):
        for app in ('ramp-peer', 'ramp-arbiter'):
            with self.subTest(app=app):
                result = self.authenticate(app)
                self.assertEqual(result, (self.wallet, self.token, None))
                self.assertIsNone(self.token.nonce)
                self.assertIsNone(self.token.nonce_expires_at)
                self.token.save.assert_called_once_with()

    def test_equivalent_public_key_encodings_are_accepted(self):
        for app in ('ramp-peer', 'ramp-arbiter'):
            with self.subTest(app=app):
                result = self.authenticate(
                    app, public_key=self.account_key.get_verifying_key()
                    .to_string('uncompressed').hex().upper(),
                )
                self.assertIs(result[0], self.wallet)

    def test_attacker_signature_with_registered_public_key_is_rejected(self):
        for app in ('ramp-peer', 'ramp-arbiter'):
            with self.subTest(app=app):
                self.assert_rejected(self.authenticate(
                    app, signer=self.attacker_key,
                    public_key=self.account_key.get_verifying_key()
                    .to_string('compressed').hex(),
                ))

    def test_invalid_keys_and_signatures_are_rejected(self):
        cases = (
            {'public_key': 'not-hex'},
            {'public_key': '00'},
            {'registered_key': 'not-hex'},
            {'registered_key': '00'},
            {'signature': 'not-hex'},
            {'signature': '00'},
        )
        for app in ('ramp-peer', 'ramp-arbiter'):
            for case in cases:
                with self.subTest(app=app, case=case):
                    self.assert_rejected(self.authenticate(app, **case))

    def test_missing_or_expired_nonce_is_rejected(self):
        for app in ('ramp-peer', 'ramp-arbiter'):
            for case in ({'nonce': None}, {'expired': True}):
                with self.subTest(app=app, case=case):
                    self.assert_rejected(self.authenticate(app, **case))

    def test_main_wallet_still_requires_an_owned_address(self):
        wallet = SimpleNamespace(addresses=Mock())
        wallet.addresses.filter.return_value.exists.return_value = False
        with patch('authentication.backends.MainWallet.objects.get', return_value=wallet), \
             patch('authentication.backends.pubkey_to_bch_address', return_value='synthetic-address'):
            result = SignatureBackend().authenticate(
                app='main', wallet_hash='synthetic-wallet', public_key='synthetic-key',
            )
        self.assertIsNone(result[0])
        self.assertIsNone(result[1])
        wallet.addresses.filter.assert_called_once_with(address='synthetic-address')
