from django.core.signing import Signer
from django.core.exceptions import ValidationError
from rampp2p.models import Peer

import binascii
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature, 
    encode_dss_signature
)

import logging
logger = logging.getLogger(__name__)

def verify_signature(wallet_hash, signature, message):
    
    # load the public key
    public_key_hex = Peer.objects.values('public_key').get(wallet_hash=wallet_hash)['public_key']
    public_key_bytes = binascii.unhexlify(public_key_hex)
    public_key = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256K1(),
        public_key_bytes
    )

    logger.warning(f'message: "{message}", public_key_hex: "{public_key_hex}", signature: "{signature}"')

    # verify the signature
    try:
        public_key.verify(
            bytes.fromhex(signature),
            message.encode(),
            ec.ECDSA(hashes.SHA256())
        )
        return True
    except InvalidSignature:
        raise ValidationError(f'Signature is invalid.')

def get_verification_headers(request):
    signature = request.headers.get('signature', None)
    timestamp = request.headers.get('timestamp', None)
    wallet_hash = request.headers.get('wallet-hash', None)
    if  (wallet_hash is None or
          signature is None or 
          timestamp is None):
        raise ValidationError('credentials not provided')
    return signature, timestamp, wallet_hash