"""Verify the chat service's existing Bitcoin signed-message webhook format."""
import base64
import binascii
from datetime import timedelta

import bitcoin
import ecdsa
from django.conf import settings
from rest_framework.exceptions import APIException, PermissionDenied


MAX_EVENT_AGE = timedelta(days=1)
MAX_FUTURE_SKEW = timedelta(minutes=5)


class ChatWebhookUnavailable(APIException):
    status_code = 503
    default_detail = 'Chat webhook verification is unavailable.'


def verify_chat_webhook(request):
    public_key = getattr(settings, 'P2P_CHAT_WEBHOOK_PUBLIC_KEY', '')
    try:
        if not isinstance(public_key, str) or len(public_key) not in (66, 128, 130):
            raise ValueError
        ecdsa.VerifyingKey.from_string(bytes.fromhex(public_key), curve=ecdsa.SECP256k1)
    except (ValueError, ecdsa.errors.MalformedPointError) as err:
        raise ChatWebhookUnavailable() from err

    signature = request.headers.get('X-Chat-Webhook-Signature', '')
    try:
        if not isinstance(signature, str) or len(signature) != 88:
            raise ValueError
        if len(base64.b64decode(signature, validate=True)) != 65:
            raise ValueError
        # Verify the original bytes, not a reserialized request.data object.
        message = request.body.decode('utf-8')
        if not bitcoin.ecdsa_verify(message, signature, public_key):
            raise ValueError
    except (ValueError, TypeError, binascii.Error, AssertionError, OverflowError) as err:
        raise PermissionDenied('Invalid chat webhook signature.') from err
