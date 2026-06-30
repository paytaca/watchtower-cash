import logging
from urllib.parse import parse_qs

from asgiref.sync import sync_to_async


logger = logging.getLogger(__name__)


class BearerTokenAuthMiddleware:
    """Channels middleware that authenticates WebSocket connections via Bearer token.

    Reads the ``?token=`` query parameter from the HTTP upgrade handshake first,
    then falls back to the ``Authorization`` header. If a valid token is
    found, ``scope['user']`` is set to a ``BitcoinCashUser`` — the same object
    type returned by ``BitcoinCashOAuthAuthentication`` in REST views.

    This middleware should be placed **inside** ``AuthMiddlewareStack`` so that
    session/cookie auth still works for browser clients, while mobile apps
    using Bearer tokens get authenticated via this layer.
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        token = self._extract_token(scope)
        if token:
            logger.info(
                f'BearerTokenAuth: attempting auth with token '
                f'{token[:16]}... (prefix: {token[:8]})'
            )
            user = await sync_to_async(self._authenticate_token)(token)
            if user is not None:
                scope['user'] = user
                logger.info(
                    f'BearerTokenAuth: authenticated user '
                    f'{user.user_id[:16]}...'
                )
            else:
                logger.warning(
                    f'BearerTokenAuth: token {token[:16]}... rejected '
                    f'(invalid/expired/revoked)'
                )
        else:
            logger.info('BearerTokenAuth: no token found in request')
        return await self.inner(scope, receive, send)

    def _extract_token(self, scope):
        # 1. Try ?token= query param first (avoids stale Authorization
        #    headers cached by the OS networking layer on mobile).
        query_string = scope.get('query_string', b'').decode()
        params = parse_qs(query_string)
        tokens = params.get('token', [])
        if tokens and tokens[0].strip():
            return tokens[0].strip()

        # 2. Fall back to Authorization header
        headers = dict(scope.get('headers', []))
        auth = headers.get(b'authorization', b'').decode()
        if auth.lower().startswith('bearer '):
            return auth[7:].strip()
        return None

    def _authenticate_token(self, token):
        try:
            from bitcoincash_oauth_django.token_manager import token_manager
            from bitcoincash_oauth_django.models import BitcoinCashUser

            token_data = token_manager.validate_access_token(token)
            if not token_data:
                return None

            return BitcoinCashUser(
                user_id=token_data.user_id,
                bitcoincash_address=token_manager.get_user_address(
                    token_data.user_id
                ),
            )
        except Exception as e:
            logger.exception(
                f'BearerTokenAuth: exception validating token '
                f'{token[:16]}...: {e}'
            )
            return None
