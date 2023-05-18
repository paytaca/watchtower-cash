from django.core.exceptions import ValidationError
from ecdsa.util import sigdecode_der, sigencode_der
from ecdsa.curves import SECP256k1
from rampp2p import tasks

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