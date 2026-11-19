"""
PyJWT 2 compatibility for `apns2` 0.7.x.

`apns2` 0.7.x builds its provider token with

    jwt.encode(...).decode("ascii")

which only works with PyJWT 1.x, where `encode()` returns `bytes`. PyJWT 2.x
returns `str`, so every token-based APNs send raised

    AttributeError: 'str' object has no attribute 'decode'

The project pins PyJWT 2.8.0 because `djangorestframework-simplejwt` 5.0.0
requires `pyjwt>=2,<3`, and `apns2` is unmaintained (0.7.2, the last release,
still decodes and still pins `PyJWT<2.0.0`). The fix therefore lives here: a
`TokenCredentials` that accepts either return type, installed over the `apns2`
class so `push_notifications` (which looks the class up on the module at call
time) and our own senders both use it.

`install()` is called from `NotificationsConfig.ready()`, so it covers the web
process, celery workers, management commands and the `push_notifications` admin
actions alike.
"""
import logging
import time

LOGGER = logging.getLogger("django")

# Not apns2's default: upstream uses 3600s, while APNs rejects provider tokens
# older than one hour, so 45 minutes leaves room for clock skew and requests
# already in flight. Overridable per instance via `token_lifetime`.
DEFAULT_TOKEN_LIFETIME = 2700
DEFAULT_TOKEN_ENCRYPTION_ALGORITHM = "ES256"


def _build_token_credentials_class(apns2_credentials):
    import jwt

    class TokenCredentials(apns2_credentials.Credentials):
        """Token-based APNs credentials that work with PyJWT 1.x and 2.x."""

        def __init__(
            self,
            auth_key_path,
            auth_key_id,
            team_id,
            encryption_algorithm=DEFAULT_TOKEN_ENCRYPTION_ALGORITHM,
            token_lifetime=DEFAULT_TOKEN_LIFETIME,
        ):
            self._auth_key = self._read_signing_key(auth_key_path)
            self._auth_key_id = auth_key_id
            self._team_id = team_id
            self._encryption_algorithm = encryption_algorithm
            self._token_lifetime = token_lifetime
            # (issued_at, token) for the cached provider token.
            self._token = None
            super().__init__()

        @staticmethod
        def _read_signing_key(key_path):
            if not key_path:
                return ""
            with open(key_path) as key_file:
                return key_file.read()

        def get_authorization_header(self, topic):
            return "bearer %s" % self._get_or_create_token()

        def _is_expired(self, issued_at):
            return time.time() > issued_at + self._token_lifetime

        def _get_or_create_token(self):
            if self._token is None or self._is_expired(self._token[0]):
                issued_at = time.time()
                token = jwt.encode(
                    {"iss": self._team_id, "iat": issued_at},
                    self._auth_key,
                    algorithm=self._encryption_algorithm,
                    headers={
                        "alg": self._encryption_algorithm,
                        "kid": self._auth_key_id,
                    },
                )
                # PyJWT 1.x returns bytes, PyJWT 2.x returns str.
                if isinstance(token, bytes):
                    token = token.decode("ascii")
                self._token = (issued_at, token)
            return self._token[1]

    return TokenCredentials


def install():
    """Replace `apns2.credentials.TokenCredentials`. Idempotent.

    Returns True when the patched class is in place.
    """
    try:
        from apns2 import credentials as apns2_credentials
    except ImportError as error:
        # APNs is unusable without apns2; the send path will fail loudly on its
        # own. Do not take the whole app down over a push transport.
        LOGGER.error(f"APNs token credentials patch skipped: {error}")
        return False

    if getattr(apns2_credentials.TokenCredentials, "_pyjwt2_safe", False):
        return True

    # Keep the upstream class reachable so the regression test can show that it
    # fails on PyJWT 2.x while the replacement does not.
    apns2_credentials._upstream_token_credentials = apns2_credentials.TokenCredentials

    token_credentials = _build_token_credentials_class(apns2_credentials)
    token_credentials._pyjwt2_safe = True
    apns2_credentials.TokenCredentials = token_credentials
    return True
