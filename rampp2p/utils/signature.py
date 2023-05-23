from django.core.exceptions import ValidationError
from rampp2p.models import Peer
from rampp2p import tasks

import hashlib
import ecdsa
from ecdsa.util import sigdecode_der
from binascii import unhexlify

import logging
logger = logging.getLogger(__name__)

def verify_signature(public_key_hex, der_signature_hex, message):
    try:

        # Convert the signature and public key to bytes
        der_signature_bytes = bytearray.fromhex(der_signature_hex)
        public_key_bytes = bytearray.fromhex(public_key_hex)

        # Create an ECDSA public key object
        vk = ecdsa.VerifyingKey.from_string(public_key_bytes, curve=ecdsa.SECP256k1)
        logger.warn(f'public_key: {public_key_hex}')
        logger.warn(f'message: {message}')

        # Verify the signature
        is_valid = vk.verify(der_signature_bytes, message.encode('utf-8'), hashlib.sha256, sigdecode=sigdecode_der)

        if is_valid:
            logger.warning("Signature is valid.")
        else:
            logger.warning("Signature is invalid.")

        return is_valid

    except Peer.DoesNotExist as err:
        raise ValidationError({"error": err.args[0]})

def decode_der_signature_hex(der_signature_hex):
    # Convert the hex-encoded DER signature to bytes:
    der_signature_bytes = bytes.fromhex(der_signature_hex)

    # Parse the DER signature using the ecdsa.util.sigdecode_der function:
    r, s = sigdecode_der(der_signature_bytes, SECP256k1.order)

    # Convert the r and s values to 32-byte integers:
    # r_bytes = r.to_bytes(32, byteorder="big")
    # s_bytes = s.to_bytes(32, byteorder="big")

    # Concatenate the r and s values to form the 65-byte signature:
    signature_bytes = sigencode_der(r, s, SECP256k1.order)

    return signature_bytes

def convert_der_to_sig(signature):
    # execute the subprocess
    path = './rampp2p/escrow/src/'
    command = 'node {}signature.js decode-sig {}'.format(
        path,
        signature
    )
    response = tasks.execute_subprocess(command)
    signature = response.get('result').get('signature')
    return signature