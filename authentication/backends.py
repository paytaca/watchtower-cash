from django.contrib.auth.backends import ModelBackend
from main.models import Wallet as MainWallet
from rampp2p.models import Peer as PeerWallet
from rampp2p.models import Arbiter as ArbiterWallet

import hashlib
import ecdsa


import logging
logger = logging.getLogger(__name__)

class SignatureBackend(ModelBackend):
    def authenticate(self, app=None, wallet_hash=None, signature=None, public_key=None):
        try:
            wallet = None
            if app == 'main':
                wallet = MainWallet.objects.get(wallet_hash=wallet_hash)
                # TODO: convert public_key to address and check if a matching address associated to wallet exists. Return if None.
            if app == 'ramp-peer':
                wallet = PeerWallet.objects.get(wallet_hash=wallet_hash)
            if app == 'ramp-arbiter':
                wallet = ArbiterWallet.objects.get(wallet_hash=wallet_hash)
            
            if wallet is not None:
                # Convert the signature and public key to bytes
                der_signature_bytes = bytearray.fromhex(signature)
                public_key_bytes = bytearray.fromhex(public_key)

                # Create an ECDSA public key object
                vk = ecdsa.VerifyingKey.from_string(public_key_bytes, curve=ecdsa.SECP256k1)

                # Verify the signature
                is_valid = vk.verify(
                    der_signature_bytes,
                    wallet.auth_nonce.encode('utf-8'),
                    hashlib.sha256,
                    sigdecode=ecdsa.util.sigdecode_der
                )

                # create auth token if signature is valid
                if is_valid and wallet.auth_token is None:
                    wallet.create_auth_token()

            return wallet
        except (MainWallet.DoesNotExist, PeerWallet.DoesNotExist, ArbiterWallet.DoesNotExist, TypeError) as err:
            logger.warn(err.args[0])