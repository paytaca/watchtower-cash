from django.conf import settings
from rest_framework import throttling

from main.utils.throttle import TokenBucket

class ScanUtxoThrottle(throttling.BaseThrottle):
    TOKEN_BUCKET_CAPACITY = 5
    TOKEN_BUCKET_RATE = 1/60
    cache = settings.REDISKV

    def get_ident(self, request, view):
        return view.kwargs.get("wallethash")

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
