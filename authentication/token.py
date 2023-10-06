from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
# from main.models import Wallet
from rampp2p.models import Peer as Wallet

import logging
logger = logging.getLogger(__name__)

class TokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get('Authorization', '').split()
        logger.warn(f'auth_header: {auth_header}')

        if len(auth_header) != 2:
            raise AuthenticationFailed('No auth credentials provided')

        if auth_header[0].lower() != 'token':
            raise AuthenticationFailed('No auth credentials provided')

        try:
            wallet = Wallet.objects.get(auth_token=auth_header[1])
        except Wallet.DoesNotExist:
            raise AuthenticationFailed('No such user')

        return (wallet, None)
