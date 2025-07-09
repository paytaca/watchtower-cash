import time
import logging
from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.authentication import BaseAuthentication
LOGGER = logging.getLogger(__name__)

from ..js_client import verify_signature

def parse_x_signature_header(header_value):
    """
    Parses a X-Signature header. 
    That is 'schnorr=abc123;der=def456' always returns a dict with both keys: { 'schnorr': '', 'der': '' }.
    """
    result = {
        'schnorr': '',
        'der': ''
    }

    if not header_value:
        return result

    parts = [kv.strip() for kv in header_value.split(';') if '=' in kv]

    for kv in parts:
        key, value = kv.split('=', 1)
        key = key.strip().lower()
        value = value.strip()
        if key in result:
            result[key] = value

    return result

def normalize_timestamp(raw_ts):
    """
    Normalize a Unix timestamp to seconds as an integer.

    Accepts seconds (e.g. 1723489212) or milliseconds (e.g. 1723489212000).
    Returns:
        int: timestamp in seconds
        None: if invalid
    """
    try:
        ts = int(raw_ts)
    except (ValueError, TypeError):
        return None

    # milliseconds
    if ts > 1e11:
        return ts // 1000
    return ts

def get_timestamp_drift_limit():
    return getattr(settings, 'MULTISIG_AUTH', {}).get('TIMESTAMP_DRIFT_SECONDS', 60)

def get_timestamp_from_auth_data(auth_data):
    message, *ignore = auth_data.split('|')
    return int(message.split(':'))

def is_valid_timestamp(timestamp: int):
    """
    Validates that the given timestamp is within the allowed drift window from current UTC time.

    Args:
        timestamp (int): The client-signed UTC timestamp in seconds.

    Raises:
        AuthenticationFailed: If the timestamp is too far in the past or future.
    """
    now = int(time.time())
    drift = get_timestamp_drift_limit()
    timestamp = normalize_timestamp(timestamp)
    if timestamp < now - drift:
        return (False, "Timestamp is too old.")
    if timestamp > now + drift:
        return (False, "Timestamp is in the future.")
    return (True, 'Timestamp valid')

class MultisigStatelessUser:
    """
    A lightweight, stateless representation of a multisig signer user.

    This class is used to represent an authenticated multisig signer during
    stateless authentication using signed messages.

    Attributes:
        wallet (MultisigWallet or None): The resolved multisig wallet
        signer (Signer or None): The resolved multisig wallet signer
        auth_data (str): Containts information to properly authentication a message in the format:

            "<message>|<public_key>|<signature>"

            Where:
                - <message> is "auth:<timestamp>" <timestamp> is a UTC Unix timestamp (e.g., 1720434000), should within range of server UTC timestamp
                - <public_key> is the compressed public key in hex format (e.g., '02ab...'), derive from xpub at address index 0
                - <signature> the signature of the message, signed using the corresponding private key of <public_key>
            This message must be signed using the corresponding private key.
            The server will parse, verify, and validate the timestamp and signature.
    """
    signer = None
    wallet = None
    auth_data = ''
    signature_verified = False

    def __init__(self, auth_data=None, signer=None, wallet=None):
        self.auth_data = auth_data
        self.signer = signer
        self.wallet = wallet
        
    def __iter__(self):
        return iter(self.__dict__.items())

    def verify_signature(self):
        if not self.auth_data:
            self.signature_verified = False
            return
        
        response = verify_signature(
            self.auth_data['message'],
            self.auth_data['public_key'],
            self.auth_data['signature']
        )

        result = response.json()
        if result['success']:
            self.signature_verified = True

    def get_public_key(self):
        if not self.auth_data:
            return ''
        return self.auth_data.get('public_key')
    


class MultisigAuthentication(BaseAuthentication):
    def authenticate(self, request):
        LOGGER.info(request.user)
        # if not request.user:
        #     raise AuthenticationFailed("Unauthorized, user must be cosigner")
        # # elif not self.user.signer:
        # #     raise AuthenticationFailed("Unauthorized, cosigner does not exist")
        # elif not request.user.auth_data:
        #     raise AuthenticationFailed("Unauthorized, missing auth data")
        
        return None
