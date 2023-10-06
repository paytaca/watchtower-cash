from django.contrib.auth.backends import ModelBackend
# from main.models import Wallet
from rampp2p.models import Peer as Wallet
import hashlib
import ecdsa

class SignatureBackend(ModelBackend):
    def authenticate(self, request, wallet_hash=None, signature=None, public_key=None):
        try:
            wallet = Wallet.objects.get(wallet_hash=wallet_hash)
            # TODO: convert public_key to address and check if a matching address associated to wallet exists. Return if None.

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

            if is_valid:
                if not wallet.auth_token:
                    wallet.create_auth_token()
                return wallet
        except Wallet.DoesNotExist:
            pass

    def get_user(self, wallet_id):
        try:
            return Wallet.objects.get(pk=wallet_id)
        except Wallet.DoesNotExist:
            return None
