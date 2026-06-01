import hashlib
import hmac
import json
from unittest.mock import patch, MagicMock

from cryptography.fernet import Fernet, InvalidToken
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from main.models import Recipient
from main.throttles import WebhookSecretThrottle
from main.utils.recipient_handler import RecipientHandler, WebhookOwnershipRequired
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
