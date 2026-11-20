"""JSON-only history caches, isolated from legacy pickle entries."""
import base64
import binascii
import json

from rest_framework.utils.encoders import JSONEncoder


CACHE_VERSION_SUFFIX = ':json-v1'


def versioned_history_cache_key(key):
    """Return the cache key used for the current JSON cache format."""
    return f'{key}{CACHE_VERSION_SUFFIX}'


def history_page_cache_key(wallet_hash, token_key, page, page_size):
    """Build the versioned cache key for one wallet-history page."""
    return versioned_history_cache_key(
        f'wallet:history:{wallet_hash}:{token_key}:{page}:{page_size}'
    )


def read_history_cache(cache, key):
    value = cache.get(key)
    if value is None:
        return None
    try:
        value = json.loads(value)
    except (ValueError, TypeError, UnicodeError):
        return None
    return value if isinstance(value, (dict, list)) else None


def write_history_cache(cache, key, value, ttl):
    try:
        encoded = json.dumps(value, cls=JSONEncoder, allow_nan=False)
    except (ValueError, TypeError, UnicodeError, OverflowError):
        return
    cache.set(key, encoded, ex=ttl)


def pos_history_cache_key(wallet_hash, params):
    encoded = json.dumps(params, sort_keys=True, separators=(',', ':'), allow_nan=False)
    encoded = base64.b64encode(encoded.encode('utf-8')).decode('ascii')
    return f'wallet:history:{wallet_hash}:pos:json-v1:{encoded}'


def pos_history_cache_params(key):
    if isinstance(key, bytes):
        try:
            key = key.decode('utf-8')
        except UnicodeError:
            return None
    marker = ':pos:json-v1:'
    if not isinstance(key, str) or marker not in key:
        return None
    try:
        value = json.loads(base64.b64decode(key.rsplit(marker, 1)[1], validate=True))
    except (ValueError, TypeError, UnicodeError, binascii.Error):
        return None
    return value if isinstance(value, dict) else None
