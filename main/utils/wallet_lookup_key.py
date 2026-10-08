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

    HMAC keyed with SECRET_KEY rather than a bare SHA-256, so that a database
    leak on its own is not enough to mount an offline lookup attack against
    anything but the digests.
    """
    return hmac.new(
        settings.SECRET_KEY.encode(),
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
