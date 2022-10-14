import math
import hmac
import hashlib
from django.utils import timezone

from ..conf import settings as app_settings

def generate_totp(secret, digits=6, interval=30, offset=0, timestamp=None):
    if timestamp is None:
        timestamp = timezone.now().timestamp()

    timecode = math.floor((timestamp - offset) / interval)

    hex_digest = hmac.new(
        secret.encode(),
        msg=str(timecode).encode(),
        digestmod=hashlib.sha256
    ).hexdigest()

    code = int(hex_digest, 16) % 10 ** digits
    code_str = str(code)
    while len(code_str) < digits:
        code_str = "0" + code_str

    return code_str


def generate_pos_device_totp(wallet_hash, posid, digits=6, interval=30, offset=0, timestamp=None):
    return generate_totp(
        f"{app_settings.TOTP_SECRET_KEY}:{wallet_hash}-{posid}",
        digits=digits, interval=interval, offset=offset, timestamp=timestamp,
    )
