from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from main.models import Wallet as MainWallet
from rampp2p.models import Peer as PeerWallet
from rampp2p.models import Arbiter as ArbiterWallet
from .models import AuthToken

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

import logging
logger = logging.getLogger(__name__)

class TokenAuthentication(BaseAuthentication):
    '''
    P2P Ramp-specific token-based authentication
    '''
    def authenticate(self, request):
        wallet_hash = request.headers.get('wallet_hash')        
        auth_header = request.headers.get('Authorization', '').split()

        if len(auth_header) != 2:
            raise AuthenticationFailed('No auth credentials provided')

        if auth_header[0].lower() != 'token':
            raise AuthenticationFailed('No auth credentials provided')

        try:
            peer_wallet = PeerWallet.objects.filter(wallet_hash=wallet_hash)
            arbiter_wallet = ArbiterWallet.objects.filter(wallet_hash=wallet_hash)

            wallet=None
            if peer_wallet.exists():
                peer_wallet = peer_wallet.first()
                if not peer_wallet.is_disabled:
                    wallet = peer_wallet
            if arbiter_wallet.exists():
                arbiter_wallet = arbiter_wallet.first()
                if not arbiter_wallet.is_disabled:
                    wallet = arbiter_wallet
            if wallet is None:
                raise AuthenticationFailed('User disabled or does not exist')
            
            auth_token = AuthToken.objects.get(wallet_hash=wallet_hash)

            cipher_suite = Fernet(settings.FERNET_KEY)
            token = cipher_suite.decrypt(auth_token.key).decode()

            if token != auth_header[1]:
                raise InvalidToken
            
            if auth_token.is_key_expired():
                raise AuthenticationFailed('Token expired')
            
        except (InvalidToken, TypeError, AuthToken.DoesNotExist):
            raise AuthenticationFailed('Invalid token')
        
        return (wallet, None)


class WalletAuthentication(BaseAuthentication):
    def get_auth_headers(self, request):
        wallet_hash = request.headers.get('wallet_hash', None)
        auth_header = request.headers.get('Authorization', '').split()
        token_key = None

        if len(auth_header) == 2:
            if auth_header[0].lower() != 'token':
                raise AuthenticationFailed('Invalid auth header')

            token_key = auth_header[1]

        return wallet_hash, token_key

    def get_auth_token(self, wallet_hash:str):
        try:
            auth_token = AuthToken.objects.get(wallet_hash=wallet_hash)
            return auth_token
        except AuthToken.DoesNotExist:
            raise AuthenticationFailed('Invalid token')

    def validate_auth_token(self, auth_token:AuthToken, token_key:str):
        cipher_suite = Fernet(settings.FERNET_KEY)
        decrypted_token_key = cipher_suite.decrypt(auth_token.key).decode()

        if decrypted_token_key != token_key:
            raise AuthenticationFailed('Invalid token')

        if auth_token.is_key_expired():
            raise AuthenticationFailed('Token expired')

    def get_wallet(self, wallet_hash):
        try:
            return MainWallet.objects.get(wallet_hash=wallet_hash)
        except MainWallet.DoesNotExist:
            raise AuthenticationFailed('No wallet found') 

    def authenticate(self, request):
        wallet_hash, token_key = self.get_auth_headers(request)

        if not wallet_hash:
            return (None, None)

        wallet = self.get_wallet(wallet_hash)

        wallet.is_authenticated = False
        if token_key:
            auth_token_obj = self.get_auth_token(wallet_hash)
            self.validate_auth_token(auth_token_obj, token_key)
            wallet.is_authenticated = True

        return (wallet, token_key) 
