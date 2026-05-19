"""
DRF Authentication class for Bitcoin Cash OAuth tokens.
Uses the package's in-memory token storage.
"""

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed


class BitcoinCashOAuthAuthentication(BaseAuthentication):
    """
    Authenticate requests using Bitcoin Cash OAuth Bearer tokens.

    Expects: Authorization: Bearer <token>

    Sets request.oauth_scopes with the token's scopes for permission checking.
    """

    keyword = "Bearer"

    def authenticate(self, request):
        auth = request.headers.get("Authorization", "")

        if not auth:
            return None

        auth_parts = auth.split()

        if len(auth_parts) != 2 or auth_parts[0].lower() != self.keyword.lower():
            return None

        token = auth_parts[1]

        # Use the package's token_manager for validation
        from bitcoincash_oauth_django.token_manager import token_manager

        token_data = token_manager.validate_access_token(token)

        if not token_data:
            raise AuthenticationFailed("Invalid or expired token.")

        # Create a simple user object from token data
        from bitcoincash_oauth_django.models import BitcoinCashUser

        user = BitcoinCashUser(
            user_id=token_data.user_id,
            bitcoincash_address=token_manager.get_user_address(token_data.user_id)
            or "",
        )

        scopes = getattr(token_data, "scopes", ["read"])

        # Expose scopes on the request for permission checking
        request.oauth_scopes = scopes

        return (user, token)

    def authenticate_header(self, request):
        """
        Return a string to be used as the value of the `WWW-Authenticate`
        header in a `401 Unauthenticated` response.
        """
        return self.keyword
