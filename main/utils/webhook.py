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


class _FailedResponse:
    """Synthetic response returned when webhook delivery cannot proceed."""
    def __init__(self, status_code=500):
        self.status_code = status_code


def send_webhook(recipient, data):
    """
    POST data to recipient.web_url.

    If the recipient has a webhook_secret, the payload is sent as JSON and
    signed with HMAC-SHA256 via the X-Watchtower-Signature header.
    Otherwise, falls back to form-encoded for backward compatibility.

    Returns the requests.Response object (or _FailedResponse on decryption error).
    """
    logger.info(f"Sending webhook to {recipient.web_url}")

    if recipient.webhook_secret:
        try:
            plaintext_secret = decrypt_webhook_secret(recipient.webhook_secret)
        except Exception:
            logger.exception(
                "Failed to decrypt webhook secret for recipient %s — skipping signed delivery",
                recipient.id,
            )
            return _FailedResponse(status_code=500)
        payload_bytes = json.dumps(data, sort_keys=True, separators=(', ', ': ')).encode('utf-8')
        sig = hmac.new(
            plaintext_secret.encode('utf-8'),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()
        try:
            return requests.post(
                recipient.web_url,
                data=payload_bytes,
                headers={
                    'Content-Type': 'application/json',
                    'X-Watchtower-Signature': f'sha256={sig}',
                },
                timeout=10,
            )
        except requests.RequestException:
            logger.exception("Network error sending signed webhook to %s", recipient.web_url)
            return _FailedResponse(status_code=599)

    try:
        return requests.post(recipient.web_url, data=data, timeout=10)
    except requests.RequestException:
        logger.exception("Network error sending webhook to %s", recipient.web_url)
        return _FailedResponse(status_code=599)
