import hashlib
import hmac
import json
import requests
import logging
logger = logging.getLogger(__name__)


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
        payload_bytes = json.dumps(data, sort_keys=True).encode('utf-8')
        sig = hmac.new(
            recipient.webhook_secret.encode('utf-8'),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()
        logger.info(f"Webhook signature: {sig}")
        return requests.post(
            recipient.web_url,
            json=data,
            headers={'X-Watchtower-Signature': f'sha256={sig}'},
        )

    return requests.post(recipient.web_url, data=data)
