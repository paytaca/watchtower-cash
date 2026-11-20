import hashlib
import hmac
import json
from pathlib import Path
import runpy
import socket
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from cryptography.fernet import Fernet
from main.test_payment_http_security import ResponseSocket, answers
from main.utils.webhook import encrypt_webhook_secret, send_webhook


class WebhookSSRFTests(TestCase):
    def setUp(self):
        self.secret = 'synthetic-webhook-secret-32-chars-long'
        key = Fernet.generate_key().decode()
        config = patch('main.utils.webhook.settings', SimpleNamespace(WEBHOOK_SECRET_KEY=key))
        config.start()
        self.addCleanup(config.stop)
        resolver = patch('main.utils.payment_http.socket.getaddrinfo', return_value=answers('8.8.8.8'))
        self.resolver = resolver.start()
        self.addCleanup(resolver.stop)
        connector = patch('main.utils.payment_http.create_connection')
        self.connect = connector.start()
        self.addCleanup(connector.stop)

    def recipient(self, url='http://merchant.example/webhook/', signed=False):
        return SimpleNamespace(
            id=42, web_url=url,
            webhook_secret=encrypt_webhook_secret(self.secret) if signed else None,
        )

    def test_signed_delivery_preserves_exact_json_bytes_and_hmac(self):
        sock = ResponseSocket(body=b'accepted')
        self.connect.return_value = sock
        data = {'txid': 'synthetic', 'amount': 1, 'address': 'synthetic-address'}
        response = send_webhook(self.recipient(signed=True), data)
        body = json.dumps(data, sort_keys=True, separators=(', ', ': ')).encode()
        signature = hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()
        request = b''.join(sock.sent)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Content-Type: application/json', request)
        self.assertIn(('X-Watchtower-Signature: sha256=' + signature).encode(), request)
        self.assertEqual(request.split(b'\r\n\r\n', 1)[1], body)

    def test_unsigned_delivery_still_uses_form_encoding(self):
        sock = ResponseSocket()
        self.connect.return_value = sock
        response = send_webhook(self.recipient(), {'txid': 'synthetic tx', 'amount': 1})
        request = b''.join(sock.sent)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Content-Type: application/x-www-form-urlencoded', request)
        self.assertNotIn(b'X-Watchtower-Signature:', request)
        self.assertEqual(request.split(b'\r\n\r\n', 1)[1], b'txid=synthetic+tx&amount=1')

    def test_unsafe_stored_urls_are_blocked_for_signed_and_unsigned_recipients(self):
        urls = ('http://127.0.0.1/', 'http://10.0.0.2/', 'http://169.254.169.254/',
                'http://[::1]/', 'http://merchant.example:3010/',
                'http://user:password@merchant.example/', 'file:///etc/passwd')
        for signed in (False, True):
            for url in urls:
                with self.subTest(signed=signed, url=url):
                    response = send_webhook(self.recipient(url, signed), {'txid': 'synthetic'})
                    self.assertEqual(response.status_code, 400)
        self.connect.assert_not_called()

    def test_private_and_mixed_dns_answers_block_delivery(self):
        for signed in (False, True):
            for result in (answers('10.0.0.2'), answers('8.8.8.8', '::1')):
                self.resolver.return_value = result
                with self.subTest(signed=signed, result=result):
                    self.assertEqual(send_webhook(self.recipient(signed=signed), {}).status_code, 400)
        self.connect.assert_not_called()

    def test_delivery_rechecks_dns_after_successful_registration(self):
        path = Path(__file__).resolve().parent / 'serializers/serializer_webhook.py'
        serializer_class = runpy.run_path(str(path))['RecipientWebhookSecretCreateSerializer']
        serializer = serializer_class(data={
            'web_url': 'http://merchant.example/webhook/', 'webhook_secret': self.secret,
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.resolver.return_value = answers('127.0.0.1')
        self.assertEqual(send_webhook(self.recipient(signed=True), {}).status_code, 400)
        self.connect.assert_not_called()

    def test_redirects_never_forward_signatures_or_payloads(self):
        for signed in (False, True):
            sock = ResponseSocket(status=307, extra_headers=b'Location: http://127.0.0.1:3010/\r\n')
            self.connect.reset_mock()
            self.connect.return_value = sock
            with self.subTest(signed=signed):
                response = send_webhook(self.recipient(signed=signed), {'txid': 'synthetic'})
                self.assertEqual(response.status_code, 400)
                self.connect.assert_called_once()
                self.assertEqual(sock.stream.body_reads, 0)

    def test_dns_and_connection_failures_remain_retryable(self):
        for signed in (False, True):
            with self.subTest(signed=signed), self.assertLogs('main.utils.webhook', level='ERROR'):
                self.resolver.side_effect = socket.gaierror('synthetic DNS outage')
                self.assertEqual(send_webhook(self.recipient(signed=signed), {}).status_code, 599)
                self.resolver.side_effect = None
                self.connect.side_effect = OSError('synthetic network outage')
                self.assertEqual(send_webhook(self.recipient(signed=signed), {}).status_code, 599)
                self.connect.side_effect = None

    def test_decryption_failure_still_returns_500_without_delivery(self):
        recipient = self.recipient()
        recipient.webhook_secret = 'invalid-synthetic-ciphertext'
        with self.assertLogs('main.utils.webhook', level='ERROR'):
            self.assertEqual(send_webhook(recipient, {}).status_code, 500)
        self.resolver.assert_not_called()
        self.connect.assert_not_called()

    def test_registration_rejects_unsafe_urls_with_field_errors(self):
        root = Path(__file__).resolve().parent / 'serializers'
        create = runpy.run_path(str(root / 'serializer_webhook.py'))['RecipientWebhookSecretCreateSerializer']
        subscribe = runpy.run_path(str(root / 'serializer_subscriber.py'))['SubscriberSerializer']
        for cls, field in ((create, 'web_url'), (subscribe, 'webhook_url')):
            for url in ('http://127.0.0.1/', 'http://10.0.0.2/', 'http://merchant.example:8080/'):
                serializer = cls(data={field: url, 'webhook_secret': self.secret})
                with self.subTest(serializer=cls.__name__, url=url):
                    self.assertFalse(serializer.is_valid())
                    self.assertIn(field, serializer.errors)
        self.connect.assert_not_called()

    def test_public_registration_preserves_exact_url_for_secret_lookup(self):
        path = Path(__file__).resolve().parent / 'serializers/serializer_webhook.py'
        cls = runpy.run_path(str(path))['RecipientWebhookSecretCreateSerializer']
        url = 'https://MERCHANT.example:443/webhook/?destination=one'
        serializer = cls(data={'web_url': url, 'webhook_secret': self.secret})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['web_url'], url)
        self.connect.assert_not_called()

    def test_subscriptions_without_webhooks_do_not_resolve_dns(self):
        path = Path(__file__).resolve().parent / 'serializers/serializer_subscriber.py'
        cls = runpy.run_path(str(path))['SubscriberSerializer']
        for data in ({'address': 'synthetic'}, {'address': 'synthetic', 'webhook_url': ''}):
            with self.subTest(data=data):
                serializer = cls(data=data)
                self.assertTrue(serializer.is_valid(), serializer.errors)
        self.resolver.assert_not_called()

    def test_legacy_url_secret_management_does_not_require_network_access(self):
        path = Path(__file__).resolve().parent / 'serializers/serializer_webhook.py'
        cls = runpy.run_path(str(path))['RecipientWebhookSecretRotateSerializer']
        serializer = cls(data={
            'web_url': 'http://10.0.0.2/', 'current_webhook_secret': self.secret,
            'new_webhook_secret': '',
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.resolver.assert_not_called()

    def test_oversized_callback_response_is_rejected(self):
        self.connect.return_value = ResponseSocket(body=b'x' * (1024 * 1024 + 1))
        self.assertEqual(send_webhook(self.recipient(), {}).status_code, 400)
