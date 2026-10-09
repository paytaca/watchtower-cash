from django.conf import settings
from rest_framework import throttling

from main.utils.throttle import TokenBucket

class ScanUtxoThrottle(throttling.BaseThrottle):
    TOKEN_BUCKET_CAPACITY = 5
    TOKEN_BUCKET_RATE = 1/60
    cache = settings.REDISKV

    def get_ident(self, request, view):
        return view.kwargs.get("wallethash") or view.kwargs.get("address")

    def get_cache_key(self, request, view):
        identity = self.get_ident(request, view)
        return f"utxo_scan_throttle:{identity}"

    def load_token_bucket(self, request, view):
        cache_key = self.get_cache_key(request, view)
        cached_data = self.cache.get(cache_key)

        try:
            self.token_bucket = TokenBucket.deserialize(cached_data)
        except (TokenBucket.InvalidTokenBucketData) as error:
            self.token_bucket = TokenBucket(self.TOKEN_BUCKET_CAPACITY, self.TOKEN_BUCKET_RATE)
        self.token_bucket.cache_key = cache_key

        return self.token_bucket

    def save_token_bucket(self):
        # cache ttl will until when the token bucket will be full
        capacity = self.token_bucket.capacity
        tokens = self.token_bucket.tokens
        rate = self.token_bucket.rate
        cache_ttl = int((capacity - tokens) / rate)

        return self.cache.set(
            self.token_bucket.cache_key,
            self.token_bucket.serialize(),
            ex=cache_ttl
        )

    def allow_request(self, request, view):
        self.load_token_bucket(request, view)
        try:
            self.token_bucket.consume(tokens=1)
        except TokenBucket.NotEnoughTokens:
            return False

        self.save_token_bucket()
        return True

    def wait(self):
        return int(self.token_bucket.get_wait_time())


class RebuildHistoryThrottle(throttling.BaseThrottle):
    TOKEN_BUCKET_CAPACITY = 2
    TOKEN_BUCKET_RATE = 1/120
    cache = settings.REDISKV

    def get_ident(self, request, view):
        return view.kwargs.get("wallethash")

    def get_cache_key(self, request, view):
        identity = self.get_ident(request, view)
        return f"rebuild_history_throttle:{identity}"

    def load_token_bucket(self, request, view):
        cache_key = self.get_cache_key(request, view)
        cached_data = self.cache.get(cache_key)

        try:
            self.token_bucket = TokenBucket.deserialize(cached_data)
        except (TokenBucket.InvalidTokenBucketData) as error:
            self.token_bucket = TokenBucket(self.TOKEN_BUCKET_CAPACITY, self.TOKEN_BUCKET_RATE)
        self.token_bucket.cache_key = cache_key

        return self.token_bucket

    def save_token_bucket(self):
        # cache ttl will until when the token bucket will be full
        capacity = self.token_bucket.capacity
        tokens = self.token_bucket.tokens
        rate = self.token_bucket.rate
        cache_ttl = int((capacity - tokens) / rate)

        return self.cache.set(
            self.token_bucket.cache_key,
            self.token_bucket.serialize(),
            ex=cache_ttl
        )

    def allow_request(self, request, view):
        self.load_token_bucket(request, view)
        try:
            self.token_bucket.consume(tokens=1)
        except TokenBucket.NotEnoughTokens:
            return False

        self.save_token_bucket()
        return True

    def wait(self):
        return int(self.token_bucket.get_wait_time())


class WebhookSecretThrottle(throttling.SimpleRateThrottle):
    """
    Throttle for POST/PATCH /recipient/webhook-secret/ — limits brute-force
    attempts against current_webhook_secret. Rate configured via
    DEFAULT_THROTTLE_RATES['webhook_secret'] in settings (default: 10/min).
    """
    scope = 'webhook_secret'

    def get_cache_key(self, request, view):
        return self.cache_format % {
            'scope': self.scope,
            'ident': self.get_ident(request),
        }


class WalletLookupKeyManageThrottle(throttling.SimpleRateThrottle):
    """
    Throttle for the wallet-authenticated mint/revoke endpoints
    (POST/DELETE /api/wallet/lookup-keys/). Rate configured via
    DEFAULT_THROTTLE_RATES['wallet_lookup_key_manage'] in settings.

    Deliberately a separate scope from WalletLookupKeyThrottle. Both buckets are
    keyed by IP, so sharing one scope meant a partner server polling balances at
    the read limit could throttle a user trying to revoke their own key -- on
    exactly the lockout path admin-side revocation exists to solve. Separate
    scopes mean read traffic can never starve the recovery path.
    """
    scope = 'wallet_lookup_key_manage'

    def get_cache_key(self, request, view):
        return self.cache_format % {
            'scope': self.scope,
            'ident': self.get_ident(request),
        }


class WalletLookupKeyThrottle(throttling.SimpleRateThrottle):
    """
    Throttle for the key-authenticated balance read endpoint
    (GET /api/wallet/lookup-keys/balances/). Rate configured via
    DEFAULT_THROTTLE_RATES['wallet_lookup_key'] in settings.

    The bucket is keyed by lookup key, not by IP. DRF runs authentication before
    check_throttles(), so by the time this is reached request.user is already the
    resolved WalletLookupKey and its identity is a better bucket key than the
    address: two partners behind one egress IP (which in production means "any
    two partners at all", since they sit behind nginx) each get their own budget
    instead of sharing one.

    Keyed by primary key, not key_hash -- the digest is a credential-derived
    secret and has no business in a cache key name that may be logged or dumped.

    Note what this does and does not do: requests that fail authentication never
    reach check_throttles() at all, so they are never metered. This bounds
    legitimate partner traffic, not credential guessing -- the key is 256 bits of
    HMAC output and is not brute-forceable.
    """
    scope = 'wallet_lookup_key'

    def get_ident(self, request, view):
        # Imported here rather than at module scope to keep this file free of
        # model imports and any load-order coupling.
        from main.models import WalletLookupKey

        user = getattr(request, 'user', None)
        # isinstance, not an is_authenticated check: LookupKeyAuthentication
        # returns a WalletLookupKey and never sets is_authenticated on it (only
        # WalletAuthentication does that, on Wallet), so the attribute-based
        # check silently fails and every request falls back to the IP bucket.
        if isinstance(user, WalletLookupKey):
            return f'key{user.pk}'
        # Unreachable via the view (authentication failures 401 before
        # throttling), but a bare request in a test must still be rate-limited
        # rather than silently exempted.
        return f'ip{super().get_ident(request)}'

    def get_cache_key(self, request, view):
        return self.cache_format % {
            'scope': self.scope,
            'ident': self.get_ident(request, view),
        }
