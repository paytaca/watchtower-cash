"""
Regression tests for the APNs provider-token path.

apns2 0.7.x builds its provider token with `jwt.encode(...).decode("ascii")`,
which breaks on PyJWT 2.x (returns `str`). The project pins PyJWT 2.8.0 for
`djangorestframework-simplejwt`, so `notifications.utils.apns_compat` installs a
version-agnostic `TokenCredentials` over the apns2 class.

These tests are version-agnostic: instead of relying on the installed PyJWT,
they drive `jwt.encode` to return a `str` (PyJWT 2.x) and assert the stock apns2
class breaks there while the installed one works.
"""
import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from apns2 import credentials as apns2_credentials

from notifications.utils import apns_compat


@pytest.fixture
def auth_key_path(tmp_path):
    key = ec.generate_private_key(ec.SECP256R1())
    path = tmp_path / "AuthKey.p8"
    path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    return str(path)


def _new_credentials(auth_key_path, token_lifetime=None):
    kwargs = {} if token_lifetime is None else {"token_lifetime": token_lifetime}
    return apns2_credentials.TokenCredentials(
        auth_key_path, "KEYID12345", "TEAMID1234", **kwargs
    )


def test_django_startup_installs_the_patched_class():
    """`NotificationsConfig.ready()` runs during setup, before any send."""
    assert getattr(
        apns2_credentials.TokenCredentials, "_pyjwt2_safe", False
    ), "apns2 TokenCredentials was not patched at app startup"
    assert apns_compat.install() is True  # idempotent


def test_patched_credentials_used_by_push_notifications_library():
    """`push_notifications` builds credentials from this module attribute."""
    from push_notifications import apns as push_apns

    assert push_apns.apns2_credentials is apns2_credentials


def _patch_jwt_encode_to_return_str(monkeypatch):
    """Make `jwt.encode` return `str`, i.e. PyJWT 2.x semantics."""
    import jwt

    real_encode = jwt.encode

    def encode_returning_str(*args, **kwargs):
        token = real_encode(*args, **kwargs)
        return token.decode("ascii") if isinstance(token, bytes) else token

    monkeypatch.setattr(jwt, "encode", encode_returning_str)


def test_upstream_class_still_fails_on_pyjwt2(auth_key_path, monkeypatch):
    """Guards the premise of the whole patch."""
    _patch_jwt_encode_to_return_str(monkeypatch)
    # The upstream class calls `super(TokenCredentials, self)`, resolving that
    # name on the apns2 module at call time; put it back for this call only.
    upstream = apns2_credentials._upstream_token_credentials
    monkeypatch.setattr(apns2_credentials, "TokenCredentials", upstream)

    with pytest.raises(AttributeError, match="no attribute 'decode'"):
        upstream(
            auth_key_path, "KEYID12345", "TEAMID1234"
        ).get_authorization_header("com.paytaca.app")


def test_patched_class_survives_pyjwt2_str_return(auth_key_path, monkeypatch):
    _patch_jwt_encode_to_return_str(monkeypatch)

    header = _new_credentials(auth_key_path).get_authorization_header(
        "com.paytaca.app"
    )

    assert isinstance(header, str)
    assert header.startswith("bearer ")
    assert header.count(".") == 2


def test_token_is_cached_between_sends(auth_key_path, monkeypatch):
    import jwt

    issued = []
    real_encode = jwt.encode

    def counting_encode(*args, **kwargs):
        issued.append(time.time())
        token = real_encode(*args, **kwargs)
        return token.decode("ascii") if isinstance(token, bytes) else token

    monkeypatch.setattr(jwt, "encode", counting_encode)

    credentials = _new_credentials(auth_key_path)
    first = credentials.get_authorization_header("com.paytaca.app")
    second = credentials.get_authorization_header("com.paytaca.app")

    assert first == second
    assert len(issued) == 1, "provider token must be reused, not rebuilt per send"


def test_token_expiry_rebuilds_at_instance_lifetime(auth_key_path, monkeypatch):
    """apns2 0.7.x ignores the instance lifetime; ours honours it."""
    import jwt

    real_encode = jwt.encode
    monkeypatch.setattr(
        jwt, "encode",
        lambda *a, **k: (
            lambda t: t.decode("ascii") if isinstance(t, bytes) else t
        )(real_encode(*a, **k)),
    )

    credentials = _new_credentials(auth_key_path, token_lifetime=0)
    credentials.get_authorization_header("com.paytaca.app")
    credential_token = credentials._token[1]
    time.sleep(0.01)
    credentials.get_authorization_header("com.paytaca.app")

    assert credentials._token[1] != credential_token


def test_signing_key_read_once_at_construction(auth_key_path, monkeypatch):
    """The key is read in `__init__`, so a send never touches the file system."""
    credentials = _new_credentials(auth_key_path)
    assert "PRIVATE KEY" in credentials._auth_key

    import os
    os.remove(auth_key_path)  # silently succeeds only if nothing re-reads it
    credentials._token = None
    assert credentials.get_authorization_header("com.paytaca.app").startswith(
        "bearer "
    )
