from rest_framework.permissions import BasePermission
from .models import AuthToken

class RampP2PIsAuthenticated(BasePermission):
    def has_permission(self, request, view):
        auth_token = AuthToken.objects.filter(wallet_hash=request.user.wallet_hash)
        is_authenticated = False
        if auth_token.exists() and not auth_token.first().is_key_expired():
            is_authenticated = True
        return request.user and is_authenticated