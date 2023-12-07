from django.contrib.auth.backends import ModelBackend
from main.models import Wallet as MainWallet
from rampp2p.models import Peer as PeerWallet
from rampp2p.models import Arbiter as ArbiterWallet
from .models import AuthToken

import hashlib
import ecdsa

import logging
logger = logging.getLogger(__name__)

class InvalidSignature(Exception):
    def __init__(self, message):
        super().__init__(message)

class SignatureBackend(ModelBackend):
    def authenticate(self, app=None, wallet_hash=None, signature=None, public_key=None):
        error = None
        wallet = None
        token = None
        try:
            if app == 'main':
                wallet = MainWallet.objects.get(wallet_hash=wallet_hash)
                # TODO: convert public_key to address and check if a matching 
                # address associated to wallet exists. Return if None.
            if app == 'ramp-peer':
                wallet = PeerWallet.objects.get(wallet_hash=wallet_hash)
            if app == 'ramp-arbiter':
                wallet = ArbiterWallet.objects.get(wallet_hash=wallet_hash)
            
            if wallet is not None:
                token = AuthToken.objects.get(wallet_hash=wallet_hash)

                if token.nonce is None:
                    raise InvalidSignature('Invalid OTP')

                # Convert the signature and public key to bytes
                der_signature_bytes = bytearray.fromhex(signature)
                public_key_bytes = bytearray.fromhex(public_key)

                # Create an ECDSA public key object
                vk = ecdsa.VerifyingKey.from_string(public_key_bytes, curve=ecdsa.SECP256k1)

                # Verify the signature
                valid = vk.verify(
                    der_signature_bytes,
                    token.nonce.encode('utf-8'),
                    hashlib.sha256,
                    sigdecode=ecdsa.util.sigdecode_der
                )

                if not valid:
                    raise InvalidSignature('Invalid signature')
                if token.is_nonce_expired():
                    raise InvalidSignature('Invalid signature: expired OTP')
                
                token.nonce = None
                token.nonce_expires_at = None
                token.save()

            return wallet, token, error
        except (MainWallet.DoesNotExist, 
                PeerWallet.DoesNotExist, 
                ArbiterWallet.DoesNotExist, 
                AuthToken.DoesNotExist,
                InvalidSignature,
                TypeError) as err:
            logger.warn(err.args[0])
            error = err.args[0]
            return None, None, error