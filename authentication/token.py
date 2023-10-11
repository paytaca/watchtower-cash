from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
# from main.models import Wallet
from rampp2p.models import Peer as Wallet

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

import logging
logger = logging.getLogger(__name__)

class TokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        wallet_hash = request.headers.get('wallet_hash')        
        auth_header = request.headers.get('Authorization', '').split()

        if len(auth_header) != 2:
            raise AuthenticationFailed('No auth credentials provided')

        if auth_header[0].lower() != 'token':
            raise AuthenticationFailed('No auth credentials provided')

        try:
            wallet = Wallet.objects.get(wallet_hash=wallet_hash)

            cipher_suite = Fernet(settings.FERNET_KEY)
            token = cipher_suite.decrypt(wallet.auth_token).decode()

            if token != auth_header[1]:
                raise InvalidToken
            
        except Wallet.DoesNotExist:
            raise AuthenticationFailed('No such user')
        except (InvalidToken, TypeError) as err:
            raise AuthenticationFailed(err.args[0])
        
        return (wallet, None)
