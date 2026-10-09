import hashlib
import hmac

from django.conf import settings
from django.utils.crypto import get_random_string

from main.models import WalletLookupKey


# Matches the entropy used by Wallet.auth_token
RAW_KEY_LENGTH = 40


def generate_raw_key() -> str:
    """Generate a new raw lookup key. Returned to the caller exactly once."""
    return get_random_string(RAW_KEY_LENGTH)


def hash_key(raw_key: str) -> str:
    """
    Derive the stored digest for a raw key.

    HMAC keyed with LOOKUP_KEY_SECRET rather than a bare SHA-256, so that a
    database leak on its own is not enough to mount an offline lookup attack
    against anything but the digests.

    LOOKUP_KEY_SECRET is a separate setting from SECRET_KEY on purpose.
    SECRET_KEY is also Django's signing key for sessions and CSRF tokens, so
    rotating it is disruptive in its own right; coupling durable credentials to
    it would mean a rotation silently invalidates every issued key, and since
    only the digest is stored the raw keys could not be recovered. See
    docs/WALLET_LOOKUP_KEYS.md.
    """
    return hmac.new(
        settings.LOOKUP_KEY_SECRET.encode(),
        raw_key.encode(),
        hashlib.sha256
    ).hexdigest()


def resolve_key(raw_key: str):
    """
    Return the WalletLookupKey matching a raw key, or None.

    A revoked key is simply absent, so there is no active/inactive filter here.
    """
    if not raw_key:
        return None

    try:
        return WalletLookupKey.objects.select_related('wallet').get(
            key_hash=hash_key(raw_key)
        )
    except WalletLookupKey.DoesNotExist:
        return None
