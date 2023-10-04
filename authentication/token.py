from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from main.models import Wallet

class TokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '').split()

        if len(auth_header) != 2:
            return None

        if auth_header[0].lower() != 'token':
            return None

        try:
            wallet = Wallet.objects.get(auth_token=auth_header[1])
        except Wallet.DoesNotExist:
            raise AuthenticationFailed('No such user')

        return (wallet, None)
