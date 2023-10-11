from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
# from main.models import Wallet
from rampp2p.models import Peer as PeerWallet
from rampp2p.models import Arbiter as ArbiterWallet

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
            elif arbiter_wallet.exists():
                arbiter_wallet = arbiter_wallet.first()
                if not arbiter_wallet.is_disabled:
                    wallet = arbiter_wallet
            else:
                raise AuthenticationFailed('User disabled or does not exist')

            cipher_suite = Fernet(settings.FERNET_KEY)
            token = cipher_suite.decrypt(wallet.auth_token).decode()

            if token != auth_header[1]:
                raise InvalidToken
            
        except (InvalidToken, TypeError):
            raise AuthenticationFailed('Invalid token')
        
        return (wallet, None)
