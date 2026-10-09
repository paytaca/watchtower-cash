import hashlib
import hmac
import inspect
import json
from io import StringIO
from unittest.mock import patch, MagicMock

import requests as requests_lib
from cryptography.fernet import Fernet, InvalidToken
from redis.exceptions import ConnectionError
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db.models import ProtectedError
from django.test import TestCase, override_settings
from django.urls import Resolver404, resolve, reverse
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory

from authentication.models import AuthToken
from main.models import (
    Recipient,
    Transaction,
    Wallet,
    Address,
    Token,
    BlockHeight,
    CashFungibleToken,
    CashNonFungibleToken,
    CashTokenInfo,
    WalletHistory,
    WalletLookupKey,
)
from main.tasks import revert_dropped_mempool_transactions
from main.throttles import (
    WalletLookupKeyManageThrottle,
    WalletLookupKeyThrottle,
    WebhookSecretThrottle,
)
from main.views.view_wallet_lookup_key import (
    WalletLookupKeyBalanceView,
    WalletLookupKeyView,
)
from main.utils.recipient_handler import RecipientHandler, WebhookOwnershipRequired, WebhookSecretRegistrationRequired
from main.utils.transaction_processing import reverse_dropped_transaction
from main.utils.wallet_balances import (
    InvalidAssetId,
    MAX_ASSETS_PER_REQUEST,
    clear_lookup_balance_cache,
    get_asset_cache_key,
    get_bch_cache_key,
    parse_asset_id,
    parse_assets_param,
)
from main.utils.wallet_lookup_key import (
    generate_raw_key,
    hash_key,
    resolve_key,
)
from main.utils.webhook import encrypt_webhook_secret, decrypt_webhook_secret, send_webhook

# Fixed Fernet key used across all webhook tests — never use in production
_TEST_FERNET_KEY = Fernet.generate_key().decode()

# Webhook secrets must be at least 32 characters
_SECRET = 'a' * 32
_NEW_SECRET = 'b' * 32

_WEBHOOK_URL = '/api/recipient/webhook-secret/'


# ---------------------------------------------------------------------------
# Encryption helpers
# ---------------------------------------------------------------------------

@override_settings(WEBHOOK_SECRET_KEY=_TEST_FERNET_KEY)
class TestWebhookEncryption(TestCase):

    def test_round_trip(self):
        ciphertext = encrypt_webhook_secret(_SECRET)
        self.assertNotEqual(ciphertext, _SECRET)
        self.assertEqual(decrypt_webhook_secret(ciphertext), _SECRET)

    def test_ciphertext_differs_each_call(self):
        # Fernet uses a random IV — two encryptions of the same plaintext are never equal
        c1 = encrypt_webhook_secret(_SECRET)
        c2 = encrypt_webhook_secret(_SECRET)
        self.assertNotEqual(c1, c2)
        self.assertEqual(decrypt_webhook_secret(c1), _SECRET)
        self.assertEqual(decrypt_webhook_secret(c2), _SECRET)

    def test_tampered_ciphertext_raises(self):
        with self.assertRaises(InvalidToken):
            decrypt_webhook_secret('not-a-valid-ciphertext')


# ---------------------------------------------------------------------------
# send_webhook
# ---------------------------------------------------------------------------

@override_settings(WEBHOOK_SECRET_KEY=_TEST_FERNET_KEY)
class TestSendWebhook(TestCase):

    def _recipient(self, secret=None):
        r = MagicMock()
        r.web_url = 'https://example.com/webhook/'
        r.webhook_secret = encrypt_webhook_secret(secret) if secret else None
        return r

    @patch('main.utils.webhook.requests.post')
    def test_signed_request_body_and_signature(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        data = {'txid': 'abc123', 'address': 'bitcoincash:qtest'}

        send_webhook(self._recipient(_SECRET), data)

        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args

        expected_body = json.dumps(data, sort_keys=True, separators=(', ', ': ')).encode('utf-8')
        self.assertEqual(kwargs['data'], expected_body)
        self.assertEqual(kwargs['headers']['Content-Type'], 'application/json')

        expected_sig = 'sha256=' + hmac.new(
            _SECRET.encode('utf-8'), expected_body, hashlib.sha256
        ).hexdigest()
        self.assertEqual(kwargs['headers']['X-Watchtower-Signature'], expected_sig)

    @patch('main.utils.webhook.requests.post')
    def test_unsigned_fallback_when_no_secret(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)

        send_webhook(self._recipient(secret=None), {'txid': 'abc'})

        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertNotIn('X-Watchtower-Signature', kwargs.get('headers', {}))

    @patch('main.utils.webhook.requests.post')
    def test_body_keys_are_sorted(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        data = {'z_last': 1, 'a_first': 2, 'm_middle': 3}

        send_webhook(self._recipient(_SECRET), data)

        _, kwargs = mock_post.call_args
        body_str = kwargs['data'].decode('utf-8')
        keys_in_order = [k for k in json.loads(body_str).keys()]
        self.assertEqual(keys_in_order, sorted(keys_in_order))


# ---------------------------------------------------------------------------
# POST /api/recipient/webhook-secret/
# ---------------------------------------------------------------------------

@override_settings(WEBHOOK_SECRET_KEY=_TEST_FERNET_KEY)
class TestRecipientWebhookSecretViewPost(TestCase):

    def setUp(self):
        self.client = APIClient()
        self._throttle = patch.object(WebhookSecretThrottle, 'allow_request', return_value=True)
        self._throttle.start()

    def tearDown(self):
        self._throttle.stop()

    def test_create_returns_201(self):
        resp = self.client.post(_WEBHOOK_URL, {
            'web_url': 'https://example.com/webhook/',
            'webhook_secret': _SECRET,
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(Recipient.objects.filter(web_url='https://example.com/webhook/').exists())

    def test_duplicate_url_returns_409(self):
        Recipient.objects.create(web_url='https://example.com/webhook/')
        resp = self.client.post(_WEBHOOK_URL, {
            'web_url': 'https://example.com/webhook/',
            'webhook_secret': _SECRET,
        }, format='json')
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data['error'], 'recipient_already_exists')

    def test_secret_too_short_returns_400(self):
        resp = self.client.post(_WEBHOOK_URL, {
            'web_url': 'https://example.com/webhook/',
            'webhook_secret': 'tooshort',
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_secret_stored_encrypted(self):
        self.client.post(_WEBHOOK_URL, {
            'web_url': 'https://example.com/webhook/',
            'webhook_secret': _SECRET,
        }, format='json')
        recipient = Recipient.objects.get(web_url='https://example.com/webhook/')
        self.assertNotEqual(recipient.webhook_secret, _SECRET)
        self.assertEqual(decrypt_webhook_secret(recipient.webhook_secret), _SECRET)


# ---------------------------------------------------------------------------
# PATCH /api/recipient/webhook-secret/
# ---------------------------------------------------------------------------

@override_settings(WEBHOOK_SECRET_KEY=_TEST_FERNET_KEY)
class TestRecipientWebhookSecretViewPatch(TestCase):

    def setUp(self):
        self.client = APIClient()
        self._throttle = patch.object(WebhookSecretThrottle, 'allow_request', return_value=True)
        self._throttle.start()
        self.web_url = 'https://example.com/webhook/'
        self.recipient = Recipient.objects.create(
            web_url=self.web_url,
            webhook_secret=encrypt_webhook_secret(_SECRET),
        )

    def tearDown(self):
        self._throttle.stop()

    def _patch(self, current, new=''):
        return self.client.patch(_WEBHOOK_URL, {
            'web_url': self.web_url,
            'current_webhook_secret': current,
            'new_webhook_secret': new,
        }, format='json')

    def test_rotate_returns_200_and_updates_secret(self):
        resp = self._patch(_SECRET, _NEW_SECRET)
        self.assertEqual(resp.status_code, 200)
        self.recipient.refresh_from_db()
        self.assertEqual(decrypt_webhook_secret(self.recipient.webhook_secret), _NEW_SECRET)

    def test_clear_secret_returns_200(self):
        resp = self._patch(_SECRET, '')
        self.assertEqual(resp.status_code, 200)
        self.recipient.refresh_from_db()
        self.assertIsNone(self.recipient.webhook_secret)

    def test_wrong_secret_returns_403(self):
        resp = self._patch('wrong_secret_but_long_enough_here', _NEW_SECRET)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data['error'], 'invalid_current_webhook_secret')

    def test_wrong_length_secret_returns_403_not_500(self):
        # Without the length-check fix, hmac.compare_digest raises ValueError → 500
        resp = self._patch('tooshort', _NEW_SECRET)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data['error'], 'invalid_current_webhook_secret')

    def test_no_secret_set_returns_403(self):
        self.recipient.webhook_secret = None
        self.recipient.save()
        resp = self._patch(_SECRET, _NEW_SECRET)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data['error'], 'no_webhook_secret_set')

    def test_unknown_url_returns_404(self):
        resp = self.client.patch(_WEBHOOK_URL, {
            'web_url': 'https://unknown.example.com/',
            'current_webhook_secret': _SECRET,
            'new_webhook_secret': _NEW_SECRET,
        }, format='json')
        self.assertEqual(resp.status_code, 404)

    def test_new_secret_too_short_returns_400(self):
        resp = self._patch(_SECRET, 'tooshort')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['error'], 'new_webhook_secret_too_short')


# ---------------------------------------------------------------------------
# RecipientHandler — DDoS / ownership protection
# ---------------------------------------------------------------------------

@override_settings(WEBHOOK_SECRET_KEY=_TEST_FERNET_KEY)
class TestRecipientHandlerOwnership(TestCase):

    def setUp(self):
        # A recipient that has claimed this URL with a secret
        Recipient.objects.create(
            web_url='https://claimed.example.com/webhook/',
            webhook_secret=encrypt_webhook_secret(_SECRET),
        )

    def test_raises_when_url_already_has_secret(self):
        handler = RecipientHandler(
            web_url='https://claimed.example.com/webhook/',
            telegram_id='attacker_telegram_id',
        )
        with self.assertRaises(WebhookOwnershipRequired):
            handler.get_or_create()

    def test_no_raise_when_url_has_no_secret(self):
        Recipient.objects.create(web_url='https://free.example.com/webhook/')
        handler = RecipientHandler(
            web_url='https://free.example.com/webhook/',
            telegram_id='some_telegram_id',
        )
        # Should not raise — existing recipient for this URL has no secret
        try:
            handler.get_or_create()
        except WebhookOwnershipRequired:
            self.fail('WebhookOwnershipRequired raised unexpectedly')


# ---------------------------------------------------------------------------
# RecipientHandler — find() path ownership check (issue #1)
# ---------------------------------------------------------------------------

@override_settings(WEBHOOK_SECRET_KEY=_TEST_FERNET_KEY)
class TestRecipientHandlerFindOwnership(TestCase):
    """
    RecipientHandler.find() returns an existing Recipient directly.
    The get_or_create() wrapper must verify ownership on that path too,
    or an attacker can subscribe arbitrary addresses to a victim URL.
    """

    def setUp(self):
        self.web_url = 'https://claimed.example.com/webhook/'
        Recipient.objects.create(
            web_url=self.web_url,
            webhook_secret=encrypt_webhook_secret(_SECRET),
        )

    def test_find_path_raises_without_secret(self):
        # Attacker provides the same web_url with no webhook_secret
        handler = RecipientHandler(web_url=self.web_url)
        with self.assertRaises(WebhookOwnershipRequired):
            handler.get_or_create()

    def test_find_path_raises_with_wrong_secret(self):
        handler = RecipientHandler(web_url=self.web_url, webhook_secret='wrong' * 8)
        with self.assertRaises(WebhookOwnershipRequired):
            handler.get_or_create()

    def test_find_path_allows_correct_secret(self):
        handler = RecipientHandler(web_url=self.web_url, webhook_secret=_SECRET)
        recipient, created = handler.get_or_create()
        self.assertFalse(created)
        self.assertEqual(recipient.web_url, self.web_url)

    def test_find_path_allows_url_with_no_secret(self):
        Recipient.objects.create(web_url='https://open.example.com/webhook/')
        handler = RecipientHandler(web_url='https://open.example.com/webhook/')
        # No secret on the existing recipient — no ownership check required
        try:
            handler.get_or_create()
        except WebhookOwnershipRequired:
            self.fail('WebhookOwnershipRequired raised unexpectedly for unsecured URL')

    def test_find_path_raises_when_secret_provided_for_unclaimed_url(self):
        # URL exists but has no secret. Caller provides a secret — we can't verify
        # ownership, so we must reject rather than silently drop the secret.
        Recipient.objects.create(web_url='https://open.example.com/webhook/')
        handler = RecipientHandler(web_url='https://open.example.com/webhook/', webhook_secret=_SECRET)
        with self.assertRaises(WebhookSecretRegistrationRequired):
            handler.get_or_create()


# ---------------------------------------------------------------------------
# send_webhook — decryption failure returns _FailedResponse (issue #5)
# ---------------------------------------------------------------------------

@override_settings(WEBHOOK_SECRET_KEY=_TEST_FERNET_KEY)
class TestSendWebhookDecryptionFailure(TestCase):

    @patch('main.utils.webhook.requests.post')
    def test_returns_500_on_invalid_ciphertext(self, mock_post):
        """
        If the stored ciphertext is malformed (e.g. key was rotated),
        send_webhook must NOT propagate the exception — it should return a
        synthetic 500 response so the caller's resp.status_code logic still
        works and the Celery task can schedule a retry instead of crashing.
        """
        r = MagicMock()
        r.id = 42
        r.web_url = 'https://example.com/webhook/'
        r.webhook_secret = 'not-a-valid-fernet-token'

        resp = send_webhook(r, {'txid': 'abc'})

        self.assertEqual(resp.status_code, 500)
        mock_post.assert_not_called()

    @patch('main.utils.webhook.requests.post', side_effect=requests_lib.exceptions.Timeout)
    def test_returns_599_on_timeout_signed(self, mock_post):
        """
        A Timeout (or any RequestException) on a signed request must not
        propagate — callers expect a .status_code, not an exception.
        599 falls into the else/retry branch in client_acknowledgement.
        """
        r = MagicMock()
        r.id = 1
        r.web_url = 'https://example.com/webhook/'
        r.webhook_secret = encrypt_webhook_secret(_SECRET)

        resp = send_webhook(r, {'txid': 'abc'})

        self.assertEqual(resp.status_code, 599)

    @patch('main.utils.webhook.requests.post', side_effect=requests_lib.exceptions.ConnectionError)
    def test_returns_599_on_network_error_unsigned(self, mock_post):
        """Same guarantee for unsigned (legacy) recipients."""
        r = MagicMock()
        r.web_url = 'https://example.com/webhook/'
        r.webhook_secret = None

        resp = send_webhook(r, {'txid': 'abc'})

        self.assertEqual(resp.status_code, 599)


# ---------------------------------------------------------------------------
# Reversing dropped (never-confirmed) transactions
# ---------------------------------------------------------------------------

class DroppedTransactionTestBase(TestCase):
    """Shared fixtures; cache helpers are stubbed so tests need no Redis."""

    def setUp(self):
        patchers = [
            patch('main.utils.transaction_processing.clear_cache_for_spent_transactions'),
            patch('main.utils.transaction_processing.clear_wallet_balance_cache'),
            patch('main.utils.transaction_processing.clear_wallet_history_cache'),
            patch('main.signals.is_bch_address', return_value=True),
        ]
        self.cache_mocks = [p.start() for p in patchers]
        self.addCleanup(lambda: [p.stop() for p in patchers])

        self.token, _ = Token.objects.get_or_create(
            name='bch', tokenid='', defaults={'token_ticker': 'BCH'}
        )
        self.wallet = Wallet.objects.create(
            wallet_hash='testwallet', wallet_type='bch', version=1
        )
        self.addr = Address.objects.create(
            address='bitcoincash:qinput', wallet=self.wallet, address_path='0/0'
        )
        self.addr2 = Address.objects.create(
            address='bitcoincash:qoutput', wallet=self.wallet, address_path='0/1'
        )

    def make_txn(self, txid, index=0, address=None, spent=False,
                 spending_txid='', blockheight=None):
        return Transaction.objects.create(
            txid=txid,
            index=index,
            address=address or self.addr,
            spent=spent,
            spending_txid=spending_txid,
            blockheight=blockheight,
            source='test',
            token=self.token,
            value=1000,
        )


class TestReverseDroppedTransaction(DroppedTransactionTestBase):

    def test_restores_spent_inputs(self):
        txn = self.make_txn('utxo_tx', spent=True, spending_txid='dropped_tx')

        reverse_dropped_transaction('dropped_tx')

        txn.refresh_from_db()
        self.assertFalse(txn.spent)
        self.assertEqual(txn.spending_txid, '')

    def test_deletes_phantom_outputs(self):
        self.make_txn('dropped_tx', address=self.addr2)

        reverse_dropped_transaction('dropped_tx')

        self.assertFalse(
            Transaction.objects.filter(txid='dropped_tx').exists()
        )

    def test_keeps_confirmed_outputs(self):
        block = BlockHeight.objects.create(number=100)
        self.make_txn('dropped_tx', address=self.addr2, blockheight=block)

        reverse_dropped_transaction('dropped_tx')

        self.assertTrue(Transaction.objects.filter(txid='dropped_tx').exists())

    def test_deletes_wallet_history(self):
        WalletHistory.objects.create(
            txid='dropped_tx', wallet=self.wallet, record_type='outgoing', amount=1
        )

        reverse_dropped_transaction('dropped_tx')

        self.assertFalse(WalletHistory.objects.filter(txid='dropped_tx').exists())

    def test_leaves_unrelated_transactions_untouched(self):
        other = self.make_txn('other_tx', spent=True, spending_txid='some_other')

        reverse_dropped_transaction('dropped_tx')

        other.refresh_from_db()
        self.assertTrue(other.spent)
        self.assertEqual(other.spending_txid, 'some_other')

    def test_recurses_into_descendants(self):
        # dropped_tx output spent by child_tx; child_tx has its own output
        self.make_txn(
            'dropped_tx', address=self.addr2, spent=True, spending_txid='child_tx'
        )
        self.make_txn('child_tx', address=self.addr2)

        reverse_dropped_transaction('dropped_tx')

        self.assertFalse(Transaction.objects.filter(txid='dropped_tx').exists())
        self.assertFalse(Transaction.objects.filter(txid='child_tx').exists())

    def test_does_not_reverse_confirmed_child(self):
        block = BlockHeight.objects.create(number=100)
        self.make_txn(
            'dropped_tx', address=self.addr2, spent=True, spending_txid='child_tx'
        )
        confirmed_child = self.make_txn('child_tx', address=self.addr2, blockheight=block)

        reverse_dropped_transaction('dropped_tx')

        self.assertTrue(Transaction.objects.filter(id=confirmed_child.id).exists())

    def test_idempotent(self):
        self.make_txn('utxo_tx', spent=True, spending_txid='dropped_tx')
        self.make_txn('dropped_tx', address=self.addr2)

        reverse_dropped_transaction('dropped_tx')
        reverse_dropped_transaction('dropped_tx')

        self.assertFalse(Transaction.objects.filter(txid='dropped_tx').exists())

    @patch.object(Transaction, 'delete', side_effect=ProtectedError('protected', []))
    def test_protected_output_is_skipped(self, mock_delete):
        self.make_txn('dropped_tx', address=self.addr2)

        summary = reverse_dropped_transaction('dropped_tx')

        self.assertEqual(summary['deleted_outputs'], 0)
        self.assertTrue(summary['protected_output_ids'])
        self.assertTrue(Transaction.objects.filter(txid='dropped_tx').exists())


class TestRevertDroppedMempoolTransactions(DroppedTransactionTestBase):

    def setUp(self):
        super().setUp()

        redis_patcher = patch('main.tasks.REDIS_STORAGE')
        self.mock_redis = redis_patcher.start()
        self.addCleanup(redis_patcher.stop)
        self.mock_redis.zrange.return_value = []

        node_patcher = patch('main.tasks.NODE.BCH.get_transaction')
        self.mock_get_tx = node_patcher.start()
        self.addCleanup(node_patcher.stop)

        reverse_patcher = patch('main.tasks.reverse_dropped_transaction')
        self.mock_reverse = reverse_patcher.start()
        self.addCleanup(reverse_patcher.stop)

    def run_sweeper(self, batch_size=10):
        return revert_dropped_mempool_transactions.apply(
            kwargs={'batch_size': batch_size}
        ).get()

    def test_reverses_tx_missing_from_node(self):
        self.make_txn('dropped_tx', address=self.addr2)
        self.mock_get_tx.return_value = None

        result = self.run_sweeper()

        self.assertIn('dropped_tx', result['reverted'])
        self.mock_reverse.assert_called_once_with('dropped_tx')
        self.mock_redis.zrem.assert_any_call('mempool:seen_txids', 'dropped_tx')

    def test_keeps_tx_still_in_mempool(self):
        self.make_txn('pending_tx', address=self.addr2)
        self.mock_get_tx.return_value = {'confirmations': 0}

        result = self.run_sweeper()

        self.assertEqual(result['reverted'], [])
        self.mock_reverse.assert_not_called()

    def test_prunes_confirmed_tx_from_tracking(self):
        self.make_txn('mined_tx', address=self.addr2)
        self.mock_get_tx.return_value = {'confirmations': 3}
        self.mock_redis.zrange.return_value = [b'mined_tx']

        result = self.run_sweeper()

        self.assertEqual(result['reverted'], [])
        self.mock_reverse.assert_not_called()
        self.mock_redis.zrem.assert_any_call('mempool:seen_txids', 'mined_tx')

    def test_reverses_tracked_tx_without_db_output_rows(self):
        # txid only exists in the Redis tracking set (all outputs untracked)
        self.mock_redis.zrange.return_value = [b'dropped_tx']
        self.mock_get_tx.return_value = None

        result = self.run_sweeper()

        self.assertIn('dropped_tx', result['reverted'])
        self.mock_reverse.assert_called_once_with('dropped_tx')

    def test_node_rpc_error_leaves_tx_for_later(self):
        self.make_txn('dropped_tx', address=self.addr2)
        self.mock_get_tx.side_effect = Exception('rpc unavailable')

        result = self.run_sweeper()

        self.assertEqual(result['reverted'], [])
        self.mock_reverse.assert_not_called()


# ---------------------------------------------------------------------------
# Wallet lookup keys
# ---------------------------------------------------------------------------

_TEST_LOOKUP_FERNET_KEY = Fernet.generate_key().decode()
_LOOKUP_URL = '/api/wallet/lookup-keys/'
_LOOKUP_BALANCES_URL = '/api/wallet/lookup-keys/balances/'

_CATEGORY = 'a' * 64
_TXID = 'b' * 64
_CATEGORY_FT = 'd' * 64
_CATEGORY_OTHER = 'e' * 64


class FakeRedis:
    """
    Minimal in-memory Redis stand-in.

    A MagicMock with `get.return_value = None` can never exercise a cache *hit*,
    which is exactly the path where the two balance endpoints used to collide.
    This actually stores values and honours SCAN, so cross-endpoint cache
    contamination is observable.
    """

    def __init__(self):
        self.store = {}

    def get(self, key, default=None):
        return self.store.get(key, default)

    def set(self, key, value, ex=None):
        self.store[key] = value
        return True

    def delete(self, *keys):
        for key in keys:
            self.store.pop(key, None)
        return True

    def scan_iter(self, match=None, count=None):
        keys = list(self.store)
        if match:
            import fnmatch
            keys = [k for k in keys if fnmatch.fnmatch(k, match)]
        return iter(keys)

    def keys(self, pattern='*'):
        return list(self.scan_iter(match=pattern))


class LookupKeyTestMixin:
    """Helpers for standing up a wallet with a valid WalletAuthentication token."""

    def _make_wallet(self, wallet_hash, wallet_type='bch'):
        wallet = Wallet.objects.create(
            wallet_hash=wallet_hash,
            wallet_type=wallet_type,
            version=1,
        )
        self._make_auth_token(wallet, 'token-for-' + wallet_hash)
        return wallet

    def _make_auth_token(self, wallet, raw_token):
        cipher = Fernet(_TEST_LOOKUP_FERNET_KEY)
        auth_token = AuthToken.objects.create(
            wallet_hash=wallet.wallet_hash,
            key=cipher.encrypt(raw_token.encode()).decode(),
            key_expires_at=timezone.now() + timezone.timedelta(days=1),
        )
        self.wallet_tokens[wallet.wallet_hash] = raw_token
        return auth_token

    def setUp(self):
        super().setUp()
        self.wallet_tokens = {}
        # A real (if tiny) store, not a MagicMock, so cache hits and the
        # cross-endpoint contamination they used to cause are observable.
        self.fake_redis = FakeRedis()
        # Saving an Address/Transaction runs main.signals.transaction_post_save,
        # which calls is_bch_address() -> an outbound HTTP request to the
        # address validator on localhost:3000. Nothing is listening in the test
        # environment, so every seeded row would raise ConnectionRefused.
        patch('main.signals.is_bch_address', return_value=False).start()
        # The signals handler reads settings.REDISKV directly, so it must see
        # the same fake store the endpoint under test uses.
        patch('main.signals.settings.REDISKV', self.fake_redis).start()
        self.addCleanup(patch.stopall)

    def _auth(self, wallet_hash):
        # WSGI-style META keys: Django's HttpHeaders resolves 'wallet-hash' and
        # 'wallet_hash' both to HTTP_WALLET_HASH.
        return {
            'HTTP_WALLET_HASH': wallet_hash,
            'HTTP_AUTHORIZATION': f"Token {self.wallet_tokens[wallet_hash]}",
        }

    def _mint(self, wallet_hash, label=''):
        resp = self.client.post(
            _LOOKUP_URL, {'label': label}, format='json', **self._auth(wallet_hash)
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        return resp.data['lookup_key']


@override_settings(FERNET_KEY=_TEST_LOOKUP_FERNET_KEY)
class TestWalletLookupKeyRouting(TestCase):
    """
    URL routing for the lookup-key endpoints. No DB or cache needed, so this
    runs in environments without Postgres.

    This exists because the balance endpoint was unreachable and every test
    still passed: unanchored re_path patterns match with re.search semantics and
    discard the unconsumed remainder, so "wallet/lookup-keys/" prefix-matched
    ".../balances/". The mint route is registered first, so balance requests
    landed on the mint view and failed its wallet authentication with 403 --
    indistinguishable from correct auth behaviour to any test that only ever
    asserted 200s and auth failures.
    """

    def test_mint_url_resolves_to_mint_view(self):
        match = resolve(reverse('wallet-lookup-keys'))
        self.assertEqual(match.func.view_class, WalletLookupKeyView)

    def test_balances_url_resolves_to_balance_view(self):
        # The regression: this resolved to WalletLookupKeyView (the mint view).
        match = resolve(reverse('wallet-lookup-key-balances'))
        self.assertEqual(match.func.view_class, WalletLookupKeyBalanceView)

    def test_balances_path_is_not_shadowed_by_the_mint_pattern(self):
        self.assertEqual(
            reverse('wallet-lookup-keys'),
            '/api/wallet/lookup-keys/',
        )
        self.assertEqual(
            reverse('wallet-lookup-key-balances'),
            '/api/wallet/lookup-keys/balances/',
        )
        self.assertNotEqual(
            reverse('wallet-lookup-keys'),
            reverse('wallet-lookup-key-balances'),
        )

    def test_unknown_subpath_under_the_prefix_is_not_routed(self):
        """
        With unanchored patterns, /balances/extra/ also resolved to the mint
        view -- junk under the prefix reached a wallet-authenticated endpoint.
        """
        with self.assertRaises(Resolver404):
            resolve('/api/wallet/lookup-keys/balances/extra/')


class TestParseAssetId(TestCase):
    """Asset id grammar. Pure, so no DB or cache needed."""

    def test_bch_is_not_a_requestable_asset_id(self):
        # The BCH balance is always returned in the top-level `bch` field, so
        # there is nothing to request. Rejected rather than silently ignored.
        for value in ('bch', 'BCH', 'Bch', ' bch '):
            with self.assertRaises(InvalidAssetId) as ctx:
                parse_asset_id(value)
            self.assertIn('always returned in the "bch" field', str(ctx.exception))

    def test_fungible_token(self):
        parsed = parse_asset_id(f'ct/{_CATEGORY}')
        self.assertEqual(parsed['type'], 'ft')
        self.assertEqual(parsed['category'], _CATEGORY)
        self.assertEqual(parsed['asset_id'], f'ct/{_CATEGORY}')

    def test_non_fungible_token(self):
        parsed = parse_asset_id(f'ct/{_CATEGORY}/{_TXID}/3')
        self.assertEqual(parsed['type'], 'nft')
        self.assertEqual(parsed['category'], _CATEGORY)
        self.assertEqual(parsed['txid'], _TXID)
        self.assertEqual(parsed['index'], 3)

    def test_slp_rejected_explicitly(self):
        # A clear error beats a silent zero balance.
        for value in ('slp/abc123', 'SLP/abc123'):
            with self.assertRaises(InvalidAssetId) as ctx:
                parse_asset_id(value)
            self.assertIn('no longer supported', str(ctx.exception))

    def test_malformed_rejected(self):
        for value in ('', '   ', 'nonsense', 'ct/', f'ct/{_CATEGORY}/{_TXID}',
                      f'ct/{_CATEGORY}/{_TXID}/1/2',
                      f'ct/{_CATEGORY}/{_TXID}/notanint', None, 123):
            with self.assertRaises(InvalidAssetId):
                parse_asset_id(value)

    def test_assets_param_split(self):
        # parse_assets_param only splits; parse_asset_id is what validates.
        other = 'c' * 64
        self.assertEqual(parse_assets_param(''), [])
        self.assertEqual(parse_assets_param(None), [])
        self.assertEqual(parse_assets_param(f'ct/{_CATEGORY}'), [f'ct/{_CATEGORY}'])
        self.assertEqual(
            parse_assets_param(f'ct/{_CATEGORY},ct/{other}'),
            [f'ct/{_CATEGORY}', f'ct/{other}'],
        )
        self.assertEqual(parse_assets_param('  '), [])


@override_settings(FERNET_KEY=_TEST_LOOKUP_FERNET_KEY)
class TestHashKey(TestCase):

    def test_digest_differs_from_raw_key(self):
        raw = generate_raw_key()
        self.assertNotEqual(hash_key(raw), raw)
        self.assertEqual(len(hash_key(raw)), 64)

    def test_deterministic_and_unique(self):
        self.assertEqual(hash_key('abc'), hash_key('abc'))
        self.assertNotEqual(hash_key('abc'), hash_key('abd'))

    def test_generated_keys_are_distinct(self):
        keys = {generate_raw_key() for _ in range(50)}
        self.assertEqual(len(keys), 50)


@override_settings(FERNET_KEY=_TEST_LOOKUP_FERNET_KEY)
class TestWalletLookupKeyMint(LookupKeyTestMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.wallet = self._make_wallet('wallet-hash-1')

    def test_mint_returns_201_and_raw_key_once(self):
        raw_key = self._mint('wallet-hash-1', label='partner-server')

        self.assertTrue(raw_key)
        row = WalletLookupKey.objects.get()
        self.assertEqual(row.label, 'partner-server')
        # Only the digest is persisted.
        self.assertNotEqual(row.key_hash, raw_key)
        self.assertEqual(row.key_hash, hash_key(raw_key))

    def test_create_response_does_not_leak_digest(self):
        resp = self.client.post(
            _LOOKUP_URL, {'label': 'x'}, format='json',
            **self._auth('wallet-hash-1')
        )
        self.assertEqual(resp.status_code, 201)
        self.assertNotIn('key_hash', resp.data)
        self.assertIn('lookup_key', resp.data)

    def test_second_mint_returns_409_and_keeps_original_key(self):
        first = self._mint('wallet-hash-1')

        resp = self.client.post(
            _LOOKUP_URL, {'label': 'second'}, format='json',
            **self._auth('wallet-hash-1')
        )

        self.assertEqual(resp.status_code, 409)
        self.assertEqual(WalletLookupKey.objects.count(), 1)
        # The existing key must still resolve.
        self.assertIsNotNone(resolve_key(first))

    def test_mint_without_token_is_rejected(self):
        # wallet-hash header alone must not be enough to mint a credential.
        resp = self.client.post(
            _LOOKUP_URL, {'label': 'x'}, format='json',
            HTTP_WALLET_HASH='wallet-hash-1',
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(WalletLookupKey.objects.count(), 0)

    def test_mint_without_wallet_hash_is_rejected(self):
        # 403, not 401: WalletAuthentication defines no authenticate_header, so
        # DRF has no challenge to send and renders PermissionDenied as 403.
        # Note this means these two read as "forbidden" when they are really
        # "unauthenticated" -- see the note on the revoke test below.
        resp = self.client.post(_LOOKUP_URL, {'label': 'x'}, format='json')
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(WalletLookupKey.objects.count(), 0)

    def test_cannot_bind_key_to_another_wallet(self):
        self._make_wallet('wallet-hash-2')
        resp = self.client.post(
            _LOOKUP_URL,
            {'label': 'x', 'wallet': 'wallet-hash-2'},
            format='json',
            **self._auth('wallet-hash-1'),
        )
        self.assertEqual(resp.status_code, 201)
        row = WalletLookupKey.objects.get()
        self.assertEqual(row.wallet.wallet_hash, 'wallet-hash-1')

    def test_one_row_per_wallet_enforced_by_db(self):
        self._mint('wallet-hash-1')
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WalletLookupKey.objects.create(
                    wallet=self.wallet, key_hash=hash_key('other')
                )


@override_settings(FERNET_KEY=_TEST_LOOKUP_FERNET_KEY)
class TestWalletLookupKeyRevoke(LookupKeyTestMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.wallet = self._make_wallet('wallet-hash-1')
        self.key = self._mint('wallet-hash-1')

    def test_revoke_returns_204_and_removes_key(self):
        resp = self.client.delete(_LOOKUP_URL, **self._auth('wallet-hash-1'))
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(WalletLookupKey.objects.count(), 0)
        self.assertIsNone(resolve_key(self.key))

    def test_second_revoke_returns_404(self):
        # Makes a blind DELETE-then-POST rotation safe to retry.
        self.client.delete(_LOOKUP_URL, **self._auth('wallet-hash-1'))
        resp = self.client.delete(_LOOKUP_URL, **self._auth('wallet-hash-1'))
        self.assertEqual(resp.status_code, 404)

    def test_revoke_without_key_returns_404(self):
        other = self._make_wallet('wallet-hash-2')
        resp = self.client.delete(_LOOKUP_URL, **self._auth('wallet-hash-2'))
        self.assertEqual(resp.status_code, 404)
        # And it must not have touched anyone else's key.
        self.assertEqual(WalletLookupKey.objects.count(), 1)
        self.assertIsNotNone(resolve_key(self.key))

    def test_cannot_revoke_another_wallets_key(self):
        self._make_wallet('wallet-hash-2')
        resp = self.client.delete(_LOOKUP_URL, **self._auth('wallet-hash-2'))
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(WalletLookupKey.objects.count(), 1)

    def test_revoke_without_token_is_rejected(self):
        # The 403 here (and in the two mint tests above) is arguably the wrong
        # code: no token was presented, so per RFC 7235 this should be 401 with a
        # WWW-Authenticate challenge. WalletAuthentication never defines
        # authenticate_header, and PermissionDenied stays 403 regardless of it,
        # so the fix belongs in that shared class -- which every wallet endpoint
        # uses, not just this one. Left alone deliberately; pinned here so the
        # current behaviour is explicit rather than incidental.
        resp = self.client.delete(_LOOKUP_URL, HTTP_WALLET_HASH='wallet-hash-1')
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(WalletLookupKey.objects.count(), 1)

    def test_rotation_yields_a_working_new_key(self):
        self.client.delete(_LOOKUP_URL, **self._auth('wallet-hash-1'))
        new_key = self._mint('wallet-hash-1', label='rotated')
        self.assertNotEqual(new_key, self.key)
        self.assertIsNone(resolve_key(self.key))
        self.assertIsNotNone(resolve_key(new_key))


@override_settings(FERNET_KEY=_TEST_LOOKUP_FERNET_KEY)
class TestWalletLookupKeyBalances(LookupKeyTestMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.wallet = self._make_wallet('wallet-hash-1')
        self.key = self._mint('wallet-hash-1')
        self.redis_patcher = patch(
            'main.utils.wallet_balances.settings.REDISKV', self.fake_redis
        )
        self.redis_patcher.start()

    def tearDown(self):
        self.redis_patcher.stop()
        super().tearDown()

    def _get(self, assets=None, key=None):
        params = {'assets': assets} if assets else {}
        return self.client.get(
            _LOOKUP_BALANCES_URL, params,
            HTTP_X_API_KEY=key if key is not None else self.key
        )

    def test_returns_bch_balance_and_wallet_hash(self):
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['wallet_hash'], 'wallet-hash-1')
        self.assertEqual(resp.data['assets'], [])
        # Assert the whole key set, not just that 'balance' is present: a
        # shape regression here would otherwise pass silently.
        self.assertEqual(
            set(resp.data['bch']),
            {'balance', 'spendable', 'valid'},
        )

    def test_returns_requested_asset_in_order(self):
        resp = self._get(assets=f'ct/{_CATEGORY},ct/{"c" * 64}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            [a['asset_id'] for a in resp.data['assets']],
            [f'ct/{_CATEGORY}', f'ct/{"c" * 64}'],
        )

    def test_bch_is_always_returned_without_being_requested(self):
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        self.assertIn('balance', resp.data['bch'])
        self.assertEqual(resp.data['assets'], [])

    def test_requesting_bch_as_an_asset_returns_400(self):
        # BCH is not an asset id -- it is always in the `bch` field.
        resp = self._get(assets='bch')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('always returned in the "bch" field', resp.data['error'])

    def test_unknown_asset_returns_zero_not_an_error(self):
        resp = self._get(assets=f'ct/{_CATEGORY}')
        self.assertEqual(resp.status_code, 200)
        entry = resp.data['assets'][0]
        self.assertEqual(entry['balance'], 0)
        self.assertFalse(entry['found'])

    def test_slp_asset_returns_400(self):
        resp = self._get(assets='slp/abc123')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('no longer supported', resp.data['error'])

    def test_malformed_asset_returns_400(self):
        resp = self._get(assets='nonsense')
        self.assertEqual(resp.status_code, 400)

    def test_missing_header_returns_401(self):
        resp = self.client.get(_LOOKUP_BALANCES_URL)
        self.assertEqual(resp.status_code, 401)

    def test_unknown_key_returns_401(self):
        resp = self._get(key='not-a-real-key')
        self.assertEqual(resp.status_code, 401)

    def test_revoked_key_returns_401(self):
        self.client.delete(_LOOKUP_URL, **self._auth('wallet-hash-1'))
        resp = self._get()
        self.assertEqual(resp.status_code, 401)

    def test_too_many_assets_returns_400(self):
        many = ','.join(f'ct/{i:064x}' for i in range(MAX_ASSETS_PER_REQUEST + 1))
        resp = self._get(assets=many)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Too many', resp.data['error'])

    def test_read_updates_last_used_at(self):
        self.assertIsNone(WalletLookupKey.objects.get().last_used_at)
        self._get()
        self.assertIsNotNone(WalletLookupKey.objects.get().last_used_at)

    def _make_nft(self, category, txid, index, with_metadata=False):
        """
        Create a CashNonFungibleToken, optionally without BCMR metadata.

        Most real NFTs have info=None: with_bcmr_metadata is a separate column
        defaulting to False, so a null info is the common case, not an edge one.
        """
        info = None
        if with_metadata:
            info = CashTokenInfo.objects.create(
                name='Cool Cat', symbol='CAT', decimals=0,
            )
        return CashNonFungibleToken.objects.create(
            category=category,
            info=info,
            current_txid=txid,
            current_index=index,
            commitment='abc123',
            capability=CashNonFungibleToken.Capability.MUTABLE,
        )

    def _make_nft_txn(self, nft, value=1):
        """An unspent Transaction so the NFT's balance query is non-zero."""
        address = Address.objects.create(
            address='bitcoincash:qnft', wallet=self.wallet, address_path='0/2'
        )
        # Transaction.token is a non-null FK, so the CashToken row needs a Token
        # even though the balance query matches on cashtoken_nft.
        token, _ = Token.objects.get_or_create(
            name='bch', tokenid='', defaults={'token_ticker': 'BCH'}
        )
        return Transaction.objects.create(
            txid=nft.current_txid,
            index=nft.current_index,
            address=address,
            spent=False,
            source='test',
            token=token,
            cashtoken_nft=nft,
            # The balance queries filter on Transaction.wallet (Q(wallet=...)),
            # not on the owning Address, so this FK is what actually scopes the
            # row to the wallet under test.
            wallet=self.wallet,
            # _get_slp_balance sums `amount`, not `value` -- the CashToken
            # quantity lives in a separate column. Seeding only `value` left
            # the balance at 0.
            value=value,
            amount=value,
        )

    def _make_ft(self, category, with_metadata=False):
        info = None
        if with_metadata:
            info = CashTokenInfo.objects.create(
                name='Some Token', symbol='TOK', decimals=2,
            )
        return CashFungibleToken.objects.create(category=category, info=info)

    def test_nft_without_metadata_does_not_500(self):
        """
        Regression: the NFT branch called get_info() unguarded, and
        CashNonFungibleToken.get_info() dereferences its nullable info FK, so a
        single metadata-less NFT raised AttributeError and 500'd the request.
        """
        nft = self._make_nft(_CATEGORY, _TXID, 0, with_metadata=False)
        self._make_nft_txn(nft)

        resp = self._get(assets=f'ct/{_CATEGORY}/{_TXID}/0')

        self.assertEqual(resp.status_code, 200, resp.data)
        entry = resp.data['assets'][0]
        self.assertTrue(entry['found'])
        self.assertEqual(entry['balance'], 1)
        # Assert the keys are present-and-None rather than absent: `found: True`
        # distinguishes "known NFT" from "unknown", and a caller must be able to
        # tell "no metadata" from "field missing".
        self.assertIn('name', entry)
        self.assertIn('symbol', entry)
        self.assertIsNone(entry['name'])
        self.assertIsNone(entry['symbol'])
        # decimals is meaningless for an NFT -- balances are 0/1, never scaled.
        self.assertEqual(entry['decimals'], 0)
        self.assertEqual(entry['commitment'], 'abc123')

    def test_nft_with_metadata_reports_name_and_symbol(self):
        """The guard must not swallow metadata when it exists."""
        nft = self._make_nft(_CATEGORY, _TXID, 0, with_metadata=True)
        self._make_nft_txn(nft)

        resp = self._get(assets=f'ct/{_CATEGORY}/{_TXID}/0')

        self.assertEqual(resp.status_code, 200, resp.data)
        entry = resp.data['assets'][0]
        self.assertEqual(entry['name'], 'Cool Cat')
        self.assertEqual(entry['symbol'], 'CAT')

    def test_metadata_less_nft_does_not_poison_other_assets(self):
        """
        The real blast radius: get_wallet_balances loops over every requested
        asset, so one bad NFT previously 500'd the whole response -- taking out
        the BCH balance and every other asset alongside it.
        """
        nft = self._make_nft(_CATEGORY, _TXID, 0, with_metadata=False)
        self._make_nft_txn(nft)
        self._make_ft(_CATEGORY_FT)
        other = _CATEGORY_OTHER

        resp = self._get(assets=(
            f'ct/{_CATEGORY_FT},'
            f'ct/{_CATEGORY}/{_TXID}/0,'
            f'ct/{other}'
        ))

        self.assertEqual(resp.status_code, 200, resp.data)
        # BCH survived.
        self.assertIn('balance', resp.data['bch'])
        self.assertEqual(resp.data['wallet_hash'], 'wallet-hash-1')
        # All three assets survived, in request order.
        self.assertEqual(
            [a['asset_id'] for a in resp.data['assets']],
            [f'ct/{_CATEGORY_FT}', f'ct/{_CATEGORY}/{_TXID}/0', f'ct/{other}'],
        )
        self.assertTrue(resp.data['assets'][0]['found'])
        self.assertTrue(resp.data['assets'][1]['found'])
        # Unknown category still reports found=False rather than erroring.
        self.assertFalse(resp.data['assets'][2]['found'])
        self.assertEqual(resp.data['assets'][2]['balance'], 0)


def _fake_request():
    return APIRequestFactory().get('/')


# The throttle writes to Django's default cache, which in tests is a
# process-global LocMemCache. This test deliberately exhausts a 600/min bucket,
# so it needs its own store or the burned budget leaks into every later test.
_THROTTLE_TEST_CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'lookup-key-throttle-scope-tests',
    }
}


@override_settings(
    FERNET_KEY=_TEST_LOOKUP_FERNET_KEY,
    CACHES=_THROTTLE_TEST_CACHES,
)
class TestWalletLookupKeyThrottleScopes(LookupKeyTestMixin, TestCase):
    """
    Mint/revoke and balance reads must not share a throttle bucket, and the read
    bucket must be keyed per lookup key rather than per IP.

    A shared scope let a partner server polling balances at the read limit
    throttle a user trying to revoke their own key -- on exactly the lockout
    path that admin-side revocation exists to solve. An IP-keyed read bucket has
    the same problem across partners: in production they are all behind nginx, so
    "same IP" means "same egress for everyone".
    """

    def setUp(self):
        super().setUp()
        self.wallet = self._make_wallet('wallet-hash-1')
        self.key = self._mint('wallet-hash-1')
        self.redis_patcher = patch(
            'main.utils.wallet_balances.settings.REDISKV', self.fake_redis
        )
        self.redis_patcher.start()

    def tearDown(self):
        self.redis_patcher.stop()
        super().tearDown()

    def _flush_throttle_cache(self):
        from django.core.cache import cache
        cache.clear()

    def _second_key(self):
        """A second wallet's key, which will be used from the same client IP."""
        self._make_wallet('wallet-hash-2')
        return self._mint('wallet-hash-2')

    def _drain_read_bucket(self, key):
        """Burn a key's whole read budget; return True once it is exhausted."""
        throttle = WalletLookupKeyThrottle()
        num_requests, _ = throttle.parse_rate(throttle.get_rate())
        for _ in range(num_requests):
            self.assertTrue(
                self.client.get(
                    _LOOKUP_BALANCES_URL, HTTP_X_API_KEY=key
                ).status_code == 200
            )
        return self.client.get(
            _LOOKUP_BALANCES_URL, HTTP_X_API_KEY=key
        ).status_code == 429

    def test_mint_and_read_use_different_scopes(self):
        manage = WalletLookupKeyManageThrottle()
        read = WalletLookupKeyThrottle()
        self.assertNotEqual(manage.scope, read.scope)
        # Both rates are configured, so neither raises at lookup time.
        for throttle in (manage, read):
            self.assertIsNotNone(throttle.get_rate())

    def test_the_two_scopes_produce_different_cache_keys(self):
        request = APIRequestFactory().get('/')
        manage_key = WalletLookupKeyManageThrottle().get_cache_key(request, None)
        read_key = WalletLookupKeyThrottle().get_cache_key(request, None)
        self.assertNotEqual(manage_key, read_key)

    def test_read_traffic_does_not_throttle_revoke(self):
        """
        The regression this guards: exhausting the read budget must leave the
        revoke path usable.

        Burns the read bucket to exhaustion -- a single shared token would not
        prove anything, since 600/min is far more than one request.
        """
        self._flush_throttle_cache()
        self.assertTrue(self._drain_read_bucket(self.key))

        # The revoke path is untouched.
        resp = self.client.delete(_LOOKUP_URL, **self._auth('wallet-hash-1'))
        self.assertEqual(
            resp.status_code, 204,
            'revoke path was throttled by balance-read traffic',
        )

    def test_one_keys_budget_does_not_throttle_another(self):
        """
        The IP-keying regression: two partners behind one egress IP must not
        share a read budget. In production every partner shares an IP, so this
        was the common case, not an edge one.
        """
        self._flush_throttle_cache()
        key2 = self._second_key()

        self.assertTrue(self._drain_read_bucket(self.key))

        # Same client IP, different key: unaffected.
        resp = self.client.get(_LOOKUP_BALANCES_URL, HTTP_X_API_KEY=key2)
        self.assertEqual(resp.status_code, 200)

    def test_cache_key_identifies_the_key_not_the_address(self):
        """Bucket identity must come from the key, and never leak the digest."""
        wallet_lookup_key = WalletLookupKey.objects.get()
        request = APIRequestFactory().get('/')
        request.user = wallet_lookup_key
        ident = WalletLookupKeyThrottle().get_ident(request, None)
        self.assertIn(str(wallet_lookup_key.pk), ident)
        self.assertNotIn(wallet_lookup_key.key_hash, ident)

    def test_ident_is_derived_from_the_key_type_not_an_attribute(self):
        """
        WalletLookupKey has no is_authenticated attribute -- only Wallet gets
        one, set dynamically by WalletAuthentication. An attribute-based check
        therefore silently falls through to the IP bucket for every read,
        which is the bug this guards.
        """
        wallet_lookup_key = WalletLookupKey.objects.get()
        self.assertFalse(hasattr(wallet_lookup_key, 'is_authenticated'))
        request = APIRequestFactory().get('/')
        request.user = wallet_lookup_key
        self.assertTrue(WalletLookupKeyThrottle().get_ident(request, None)
                        .startswith('key'))

    def test_unauthenticated_request_still_gets_a_bucket(self):
        """
        Authentication failures 401 before throttling, so this path is
        unreachable via the view -- but a bare request must be rate-limited
        rather than silently exempted by a None ident.
        """
        request = APIRequestFactory().get('/')
        ident = WalletLookupKeyThrottle().get_ident(request, None)
        self.assertIsNotNone(ident)


@override_settings(FERNET_KEY=_TEST_LOOKUP_FERNET_KEY)
class TestWalletLookupKeyCacheIsolation(LookupKeyTestMixin, TestCase):
    """
    The lookup-key balance endpoint and the pre-existing /api/balance/wallet/
    endpoint used to share Redis keys while writing *different* payload shapes.
    Both replace their entire response with whatever they read back, so a
    lookup-key read could silently strip fields from the balance endpoint and
    vice versa. These tests pin the isolation.
    """

    # What the pre-existing balance endpoint puts in its cache and returns.
    LEGACY_BCH_KEYS = {'valid', 'wallet', 'spendable', 'balance', 'yield'}
    LEGACY_TOKEN_KEYS = {'valid', 'wallet', 'balance', 'spendable', 'token_id'}

    def setUp(self):
        super().setUp()
        self.wallet = self._make_wallet('wallet-hash-1')
        self.key = self._mint('wallet-hash-1')
        self.redis_patcher = patch(
            'main.utils.wallet_balances.settings.REDISKV', self.fake_redis
        )
        self.redis_patcher.start()

    def tearDown(self):
        self.redis_patcher.stop()
        super().tearDown()

    def test_lookup_writes_its_own_namespace(self):
        self.client.get(_LOOKUP_BALANCES_URL, HTTP_X_API_KEY=self.key)
        written = list(self.fake_redis.keys())
        self.assertTrue(written, 'expected the lookup read to populate the cache')
        for key in written:
            self.assertTrue(
                key.startswith('lookup:balance:'),
                f'lookup endpoint wrote outside its namespace: {key}',
            )

    def test_does_not_write_legacy_balance_keys(self):
        self.client.get(
            _LOOKUP_BALANCES_URL,
            {'assets': f'ct/{_CATEGORY}'},
            HTTP_X_API_KEY=self.key,
        )
        for key in self.fake_redis.keys():
            self.assertFalse(
                key.startswith('wallet:balance:'),
                f'lookup endpoint polluted the balance endpoint cache: {key}',
            )

    def test_lookup_cannot_read_the_balance_endpoints_payload(self):
        """
        Reverse direction: the balance endpoint's payload must be unreadable
        here, because it lives under a different namespace entirely.

        Note this writes to `wallet:balance:*` -- the *balance* endpoint's key --
        rather than to a lookup key. An earlier version of this test planted the
        foreign payload directly on a lookup key, which asserted that a cache
        hit under our own namespace magically gains `found`/`decimals`. That is
        not true and not what namespacing promises: a hit under our namespace is
        our own payload, because nothing else writes there.
        """
        self.fake_redis.store[
            f'wallet:balance:token:wallet-hash-1:{_CATEGORY}'
        ] = json.dumps({
            'balance': 5.0, 'spendable': 5.0, 'token_id': _CATEGORY,
            'valid': True,
        })

        resp = self.client.get(
            _LOOKUP_BALANCES_URL,
            {'assets': f'ct/{_CATEGORY}'},
            HTTP_X_API_KEY=self.key,
        )

        self.assertEqual(resp.status_code, 200)
        entry = resp.data['assets'][0]
        # Recomputed from the database under our own key, so the lookup contract
        # holds: 'token_id'/'spendable'/'valid' are not borrowed from the
        # balance endpoint's payload.
        self.assertNotIn('token_id', entry)
        self.assertNotIn('spendable', entry)
        self.assertIn('found', entry)
        self.assertIn('decimals', entry)
        # And the balance endpoint's entry was left alone.
        stored = json.loads(
            self.fake_redis.store[f'wallet:balance:token:wallet-hash-1:{_CATEGORY}']
        )
        self.assertEqual(stored['token_id'], _CATEGORY)

    def test_two_nfts_in_one_category_do_not_collide(self):
        """
        Keying the NFT cache by category alone makes every NFT in a category
        share one slot, so the second read returns the first NFT's balance.
        """
        txid2 = 'd' * 64
        id1 = f'ct/{_CATEGORY}/{_TXID}/0'
        id2 = f'ct/{_CATEGORY}/{txid2}/1'

        first = self.client.get(
            _LOOKUP_BALANCES_URL, {'assets': id1}, HTTP_X_API_KEY=self.key
        )
        self.assertEqual(first.status_code, 200)

        # Warm the slot for NFT #1, then request NFT #2 from the same category.
        second = self.client.get(
            _LOOKUP_BALANCES_URL, {'assets': id2}, HTTP_X_API_KEY=self.key
        )
        self.assertEqual(second.status_code, 200)

        self.assertEqual(second.data['assets'][0]['asset_id'],
                         f'ct/{_CATEGORY}/{txid2}/1')

        keys = [k for k in self.fake_redis.keys() if 'nft' in k]
        self.assertEqual(len(keys), 2, f'NFTs shared a cache slot: {keys}')


@override_settings(FERNET_KEY=_TEST_LOOKUP_FERNET_KEY)
class TestLookupBalanceCacheInvalidation(LookupKeyTestMixin, TestCase):
    """
    clear_lookup_balance_cache must drop exactly one wallet's cached balances.

    Shared by the revoke endpoint and the revoke_lookup_key command so the two
    cannot drift; these tests pin the glob itself.
    """

    def setUp(self):
        super().setUp()
        self.wallet = self._make_wallet('wallet-hash-1')
        # A sibling hash that shares a string prefix with wallet-hash-1.
        self.sibling = self._make_wallet('wallet-hash-10')

    def _keys_for(self, wallet, descriptor=None):
        """Seed and return the cache keys one wallet would produce."""
        if descriptor is None:
            keys = [get_bch_cache_key(wallet)]
        else:
            keys = [get_asset_cache_key(wallet, descriptor)]
        for key in keys:
            self.fake_redis.set(key, '{}')
        return keys

    def _ft(self, category='catA'):
        return {'type': 'ft', 'category': category}

    def _nft(self, category='catB', txid='aa', index=0):
        return {'type': 'nft', 'category': category, 'txid': txid,
                'index': index}

    def test_clears_bch_ft_and_nft_keys(self):
        """All three key shapes must go. The bch key is the easy one to miss."""
        bch = self._keys_for(self.wallet)
        ft = self._keys_for(self.wallet, self._ft())
        nft = self._keys_for(self.wallet, self._nft())

        clear_lookup_balance_cache('wallet-hash-1', cache=self.fake_redis)

        for key in bch + ft + nft:
            self.assertNotIn(key, self.fake_redis.store,
                             f'cache key survived invalidation: {key}')

    def test_does_not_evict_a_hash_that_shares_a_prefix(self):
        """
        The regression this guards.

        wallet_hash is a free-form CharField, so 'wallet-hash-1' and
        'wallet-hash-10' are both legal. A glob ending in a bare '*' matches the
        sibling too, which was harmless but unbounded.
        """
        sibling_bch = self._keys_for(self.sibling)
        sibling_ft = self._keys_for(self.sibling, self._ft())
        self._keys_for(self.wallet)

        clear_lookup_balance_cache('wallet-hash-1', cache=self.fake_redis)

        for key in sibling_bch + sibling_ft:
            self.assertIn(
                key, self.fake_redis.store,
                'invalidating one wallet evicted a prefix-sharing sibling',
            )

    def test_is_a_noop_for_a_wallet_with_nothing_cached(self):
        """No keys cached must not raise -- revoke has to survive this."""
        clear_lookup_balance_cache('wallet-hash-never-cached',
                                   cache=self.fake_redis)

    def test_survives_a_broken_cache(self):
        """A cache failure must never fail a revocation."""
        class Exploding:
            def delete(self, *a, **kw):
                raise ConnectionError('redis down')

            def scan_iter(self, *a, **kw):
                raise ConnectionError('redis down')

        clear_lookup_balance_cache('wallet-hash-1', cache=Exploding())

    def test_view_and_command_share_one_implementation(self):
        """Guards against the two call sites drifting back into copies."""
        from main.management.commands.revoke_lookup_key import (
            Command as RevokeCommand,
        )
        view_src = inspect.getsource(WalletLookupKeyView)
        cmd_src = inspect.getsource(RevokeCommand)
        for name, src in (('view', view_src), ('command', cmd_src)):
            self.assertNotIn(
                'scan_keys', src,
                f'{name} reimplements the glob instead of calling the helper',
            )
            self.assertIn(
                'clear_lookup_balance_cache', src,
                f'{name} should call the shared helper',
            )


@override_settings(FERNET_KEY=_TEST_LOOKUP_FERNET_KEY)
class TestWalletLookupKeyAdmin(LookupKeyTestMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.wallet = self._make_wallet('wallet-hash-1')
        self.key = self._mint('wallet-hash-1')
        self.admin_user = User.objects.create_superuser(
            username='admin', email='admin@example.com', password='pw'
        )
        self.client.force_login(self.admin_user)

    def test_admin_can_delete_a_key_for_a_locked_out_wallet(self):
        pk = WalletLookupKey.objects.get().pk
        resp = self.client.post(
            reverse('admin:main_walletlookupkey_delete', args=[pk]),
            {'post': 'yes'},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(WalletLookupKey.objects.count(), 0)
        self.assertIsNone(resolve_key(self.key))

    def test_admin_changelist_searches_by_wallet_hash(self):
        resp = self.client.get(
            reverse('admin:main_walletlookupkey_changelist') + '?q=wallet-hash-1'
        )
        self.assertEqual(resp.status_code, 200)


@override_settings(FERNET_KEY=_TEST_LOOKUP_FERNET_KEY)
class TestRevokeLookupKeyCommand(LookupKeyTestMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.wallet = self._make_wallet('wallet-hash-1')
        self.key = self._mint('wallet-hash-1')

    def _run(self, *args, **kwargs):
        out = StringIO()
        call_command('revoke_lookup_key', *args, stdout=out, **kwargs)
        return out.getvalue()

    def test_revokes_by_wallet_hash(self):
        output = self._run('wallet-hash-1')
        self.assertIn('revoked', output)
        self.assertEqual(WalletLookupKey.objects.count(), 0)
        self.assertIsNone(resolve_key(self.key))

    def test_dry_run_leaves_the_key_in_place(self):
        output = self._run('wallet-hash-1', dry_run=True)
        self.assertIn('would revoke', output)
        self.assertEqual(WalletLookupKey.objects.count(), 1)

    def test_reports_wallet_without_a_key(self):
        self._make_wallet('wallet-hash-2')
        output = self._run('wallet-hash-2')
        self.assertIn('no lookup key', output)
        self.assertEqual(WalletLookupKey.objects.count(), 1)

    def test_handles_multiple_wallet_hashes(self):
        self._make_wallet('wallet-hash-2')
        self._mint('wallet-hash-2')
        self._run('wallet-hash-1', 'wallet-hash-2')
        self.assertEqual(WalletLookupKey.objects.count(), 0)
