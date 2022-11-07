from django.utils import timezone as tz

class TokenBucket:
    """
        Token bucket algorithm with de/serialization functions
    """
    class NotEnoughTokens(Exception):
        pass

    class InvalidTokenBucketData(Exception):
        pass

    def __init__(self, capacity, rate, last_consume=0, tokens=None):
        self.capacity = capacity
        self.rate = rate

        if tokens is None:
            self.tokens = capacity
        else:
            self.tokens = tokens

        self.last_consume = last_consume


    def consume(self, tokens=1):
        if tokens > self.capacity:
            raise self.NotEnoughTokens("Tokens to consume exceeded capacity")

        now = tz.now().timestamp()
        lapse = now - self.last_consume
        current_tokens = self.tokens + lapse * self.rate
        if current_tokens > self.capacity:
            current_tokens = self.capacity

        if current_tokens < tokens:
            raise self.NotEnoughTokens("Not enough tokens in bucket")

        current_tokens -= tokens
        self.tokens = current_tokens
        self.last_consume = now

    def get_wait_time(self, tokens=1):
        now = tz.now().timestamp()
        lapse = now - self.last_consume
        current_tokens = self.tokens + lapse * self.rate
        needed_tokens = tokens - current_tokens
        if needed_tokens <= 0:
            return 0

        return needed_tokens / self.rate

    def serialize(self):
        return f"{self.capacity}|{self.rate}|{self.tokens}|{self.last_consume}"

    @classmethod
    def deserialize(cls, data):
        if not isinstance(data, str) and not isinstance(data, bytes):
            raise cls.InvalidTokenBucketData("Expected string/bytes type")

        if isinstance(data, bytes):
            data = data.decode()

        tokenized_data = data.split("|")
        if len(tokenized_data) < 2:
            raise cls.InvalidTokenBucketData("Invalid data")

        capacity = None
        rate = None
        tokens = None
        last_consume = 0

        try:
            capacity = float(tokenized_data[0])
        except (TypeError, ValueError):
            raise cls.InvalidTokenBucketData(f"Invalid capacity value {tokenized_data[0]}")

        try:
            rate = float(tokenized_data[1])
        except (TypeError, ValueError):
            raise cls.InvalidTokenBucketData(f"Invalid rate value {tokenized_data[1]}")

        try:
            tokens = float(tokenized_data[2])
        except (TypeError, ValueError):
            tokens = None
        
        try:
            last_consume = float(tokenized_data[3])
        except (TypeError, ValueError):
            last_consume = 0

        return cls(capacity, rate, tokens=tokens, last_consume=last_consume)
