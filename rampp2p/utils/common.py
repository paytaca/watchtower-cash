from django.core.signing import Signer
from django.core.exceptions import ValidationError

def verify_signature(wallet_hash, pubkey, signature, message):
    print('verify_signature')
    # signer = Signer(pubkey)
    # try:
    #     signed_message = signer.unsign(signature)
    #     if signed_message != message:
    #         raise ValidationError('Signature is invalid')
    # except:
    #     raise ValidationError('Signature is invalid')  

    # TODO: derive the address from the public key
    # TODO: address must be registered under the Wallet with field wallet_hash=wallet_hash

def get_verification_headers(request):
    pubkey = request.headers.get('pubkey', None)
    signature = request.headers.get('signature', None)
    timestamp = request.headers.get('timestamp', None)
    wallet_hash = request.headers.get('wallet-hash', None)
    if  wallet_hash is None or pubkey is None or signature is None or timestamp is None:
        raise ValidationError('credentials not provided')
    return pubkey, signature, timestamp, wallet_hash