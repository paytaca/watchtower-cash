import time
import logging
from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.authentication import BaseAuthentication
from django.conf import settings
from django.urls import resolve
from ..utils import derive_pubkey_from_xpub
from ..models import MultisigWallet


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

def parse_signatures(signature):
    """
    Parses a signature string 
    That is 'schnorr=abc123;der=def456' always returns a dict with both keys: { 'schnorr': '', 'der': '' }.
    """
    return parse_x_signature_header(signature)


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
    return getattr(settings, 'MULTISIG', {}).get('TIMESTAMP_DRIFT_SECONDS', 120)

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
        return (False, f"Message timestamp too old. Value must be ±{drift}s from current UTC time.")
    if timestamp > now + drift:
        return (False, f"Message timestamp drifted too far into the future. Value must be ±{drift}s from current UTC time.")
    return (True, 'Ok')

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
                - <message> is "<context>:<timestamp>" <timestamp> is a UTC Unix timestamp (e.g., 1720434000), should within range of server UTC timestamp
                - <public_key> is the compressed public key in hex format (e.g., '02ab...'), derive from xpub at address index 0
                - <signature> the signature of the message, signed using the corresponding private key of <public_key>
            This message must be signed using the corresponding private key.
            The server will parse, verify, and validate the timestamp and signature.
    """
    signer = None
    wallet = None
    auth_data = None
    signature_verified = None

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
    

class PubKeySignatureMessageAuthentication(BaseAuthentication):
    """
    Authenticates a request by verifying a detached digital signature using a public key.

    This authentication method is stateless and does not associate the request with a User.
    It validates the integrity and freshness of a signed message (typically for proving identity or intent)
    based on headers provided in the request.

    Expected headers:
        - X-Auth-Message: A string in the format '<context>:<timestamp>' e.g. multisig:1720434000, any:1720434000
        - X-Auth-PubKey: The public key that corresponds to the private key used to sign the message
        - X-Auth-Signature: The detached signature of the message with the ff format: 'schnorr=<signature>;der=<signature>'

    Behavior:
        - If any of the required headers are missing, the authentication class will return None
          and allow other authentication classes to try.
        - If the timestamp is outside the allowed drift range, the request is rejected with a 401 error.
        - If the signature verification fails, the request is rejected with a 401 error.
        - On successful verification, the request is considered authenticated (but anonymous), and
          `(None, None)` is returned.

    Notes:
        - Signature verification is delegated to `verify_signature()`.
        - Timestamp drift is validated using `is_valid_timestamp()`.
        - This class is intended for use in systems that require stateless authentication without the need for user account

    Returns:
        - (None, None) on success, to indicate authentication passed without assigning a user.
        - None if the signature headers are not present.
        - Raises AuthenticationFailed if the message is expired or signature is invalid.
    """
    
    def authenticate(self, request):
       
        message = request.headers.get('X-Auth-Message', '')

        if message:
            timestamp = message.split(':')[1]
            is_valid, error = is_valid_timestamp(int(timestamp)) # short circuits if timestamp is > ±drift
            if not is_valid:
                raise AuthenticationFailed(error)

        public_key = request.headers.get('X-Auth-PubKey', '')
        signature = request.headers.get('X-Auth-Signature', '')

        if not signature or not message or not public_key:
            raise AuthenticationFailed('Invalid credentials')
        
        signature = parse_x_signature_header(signature)

        sig_verification_response = verify_signature(message, public_key, signature)
        sig_verification_result = sig_verification_response.json()

        if not sig_verification_result['success']:
            raise AuthenticationFailed('Invalid signature')
        return None

class MultisigAuthentication(BaseAuthentication):
    
    def authenticate(self, request):
    
        if not request.path.startswith('/api/multisig'):
            return None
        
        message = request.headers.get('X-Auth-Message', '')
        
        if not message or message.split(':')[0] != 'multisig':
            raise AuthenticationFailed('Invalid credential, invalid value for message')

        if getattr(settings, 'MULTISIG', {}).get('ENABLE_AUTH', False) == False:
            return (None, None)

        public_key = request.headers.get('X-Auth-PubKey', '')
        signature = request.headers.get('X-Auth-Signature', '')
        if not public_key or not signature:
            raise AuthenticationFailed('Invalid credentials, missing public key or signature')

        if not hasattr(request, 'resolver_match') or request.resolver_match == None:
            request.resolver_match = resolve(request.path_info)

        wallet_identifier = request.resolver_match.kwargs.get('wallet_identifier')
        proposal_identifier = request.resolver_match.kwargs.get('proposal_identifier')  
        
        wallet = None 
        signer = None

        if wallet_identifier:
            if wallet_identifier.isdigit():
                wallet = MultisigWallet.objects.prefetch_related('signers').filter(id = int(wallet_identifier)).first()
            else:
                wallet = MultisigWallet.objects.prefetch_related('signers').filter(locking_bytecode=wallet_identifier).first()
        elif proposal_identifier:
            if proposal_identifier.isdigit():
                wallet = MultisigWallet.objects.prefetch_related('signers').filter(multisigtransactionproposal__id=int(proposal_identifier)).first()
            else:
                wallet = MultisigWallet.objects.prefetch_related('signers').filter(multisigtransactionproposal__locking_bytecode=proposal_identifier).first()        
        
        user = MultisigStatelessUser(wallet=wallet)


        if wallet and public_key:
            for signer in wallet.signers.all():
                derived_public_key = derive_pubkey_from_xpub(signer.xpub, 0)
                if public_key == derived_public_key:
                    user.signer = signer
                    break 
        
        user.wallet = wallet
        user.auth_data = {
            'public_key': public_key,
            'message': message,
            'signature': parse_x_signature_header(signature)
        }
        return (user, user.auth_data)
        
