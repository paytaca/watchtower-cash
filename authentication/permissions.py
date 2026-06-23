from rest_framework.permissions import BasePermission
from .models import AuthToken, ApiToken

class RampP2PIsAuthenticated(BasePermission):
    def has_permission(self, request, view):
        auth_token = AuthToken.objects.filter(wallet_hash=request.user.wallet_hash)
        is_authenticated = False
        if auth_token.exists() and not auth_token.first().is_key_expired():
            is_authenticated = True
        return request.user and is_authenticated


class BaseHasApiTokenScopePermission(BasePermission):
    scopes = []
    match_all = False

    def has_permission(self, request, view):
        api_token = getattr(request, "api_token", None)
        if not isinstance(api_token, ApiToken):
            return False

        token_scopes = api_token.scopes
        matches = [scope in token_scopes for scope in self.scopes]
        if self.match_all:
            return all(matches)
        else:
            return any(matches)


def HasApiTokenScopePermission(name:str = "", scopes:list= [], match_all:bool = False):
    return type(name, (BaseHasApiTokenScopePermission,), dict(
        scopes=scopes,
        match_all=match_all,
    ))
