from django.core.exceptions import ValidationError
from rampp2p.models import Peer
import ecdsa
import hashlib

import logging
logger = logging.getLogger(__name__)

def verify_signature(wallet_hash, signature_hex, message, **kwargs):
    # return True
    try:
        public_key_hex = kwargs.get('public_key')
        if public_key_hex is None:
            peer = Peer.objects.get(wallet_hash=wallet_hash)
            public_key_hex = peer.public_key

        # Convert the signature and public key to bytes
        der_signature_bytes = bytearray.fromhex(signature_hex)
        public_key_bytes = bytearray.fromhex(public_key_hex)

        # Create an ECDSA public key object
        vk = ecdsa.VerifyingKey.from_string(public_key_bytes, curve=ecdsa.SECP256k1)
        # logger.warn(f'wallet_hash: {wallet_hash}')
        # logger.warn(f'signature_hex: {signature_hex}')
        # logger.warn(f'public_key: {public_key_hex}')
        # logger.warn(f'message: {message}')

        # Verify the signature
        is_valid = vk.verify(der_signature_bytes, message.encode('utf-8'), hashlib.sha256, sigdecode=ecdsa.util.sigdecode_der)

        return is_valid

    except (Peer.DoesNotExist, Exception) as err:
        raise ValidationError({"error": err.args[0]})

def get_verification_headers(request):
    logger.warn(f'headers: {request.headers}')
    signature = request.headers.get('signature', None)
    timestamp = request.headers.get('timestamp', None)
    wallet_hash = request.headers.get('wallet_hash', None)
    if  (wallet_hash is None or
          signature is None or 
          timestamp is None):
        raise ValidationError('credentials not provided')
    return signature, timestamp, wallet_hash