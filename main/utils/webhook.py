import hashlib
import hmac
import json
import requests
import logging

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


def _get_fernet():
    key = getattr(settings, 'WEBHOOK_SECRET_KEY', None)
    if not key:
        raise ImproperlyConfigured(
            'WEBHOOK_SECRET_KEY must be set to use webhook secret encryption. '
            'Generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_webhook_secret(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode('utf-8')).decode('utf-8')


def decrypt_webhook_secret(ciphertext: str) -> str:
    return _get_fernet().decrypt(ciphertext.encode('utf-8')).decode('utf-8')


def send_webhook(recipient, data):
    """
    POST data to recipient.web_url.

    If the recipient has a webhook_secret, the payload is sent as JSON and
    signed with HMAC-SHA256 via the X-Watchtower-Signature header.
    Otherwise, falls back to form-encoded for backward compatibility.

    Returns the requests.Response object.
    """
    logger.info(f"Sending webhook to {recipient.web_url} with data: {data}")

    if recipient.webhook_secret:
        plaintext_secret = decrypt_webhook_secret(recipient.webhook_secret)
        payload_bytes = json.dumps(data, sort_keys=True, separators=(', ', ': ')).encode('utf-8')
        sig = hmac.new(
            plaintext_secret.encode('utf-8'),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()
        return requests.post(
            recipient.web_url,
            data=payload_bytes,
            headers={
                'Content-Type': 'application/json',
                'X-Watchtower-Signature': f'sha256={sig}',
            },
        )

    return requests.post(recipient.web_url, data=data)
