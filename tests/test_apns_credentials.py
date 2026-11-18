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
import os
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

    # Deleting the file must not matter: if anything re-read it, this raises.
    import os

    os.remove(auth_key_path)
    credentials._token = None
    assert credentials.get_authorization_header("com.paytaca.app").startswith(
        "bearer "
    )


# --- settings shape ---------------------------------------------------------
# The rules live in `watchtower.apns_settings` because importing the project's
# settings module pulls in every app; these exercise the builder directly.

def _build(monkeypatch, env, base_dir="/code"):
    """Call the builder with `os.environ` as the only config source.

    Backed by a real `decouple.Config` over an empty repository rather than a
    stub, so the casts under test are the ones that run in production. The
    repository is emptied because `decouple` otherwise reads `.env` from the
    working directory and the developer's own settings leak in.
    """
    for name in (
        "APNS_AUTH_KEY_PATH",
        "APNS_AUTH_KEY_ID",
        "APNS_TEAM_ID",
        "APNS_TOPIC",
        "APNS_USE_ALTERNATIVE_PORT",
        "APNS_USE_SANDBOX",
        "BCH_NETWORK",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    from decouple import Config, RepositoryEmpty

    from watchtower import apns_settings

    monkeypatch.setattr(apns_settings, "config", Config(RepositoryEmpty()))
    return apns_settings.build_apns_settings(base_dir)


def test_mainnet_uses_production_host_and_configured_key(monkeypatch):
    apns = _build(
        monkeypatch,
        {
            "BCH_NETWORK": "mainnet",
            "APNS_AUTH_KEY_PATH": "compose/APNS_AuthKey.p8",
            "APNS_AUTH_KEY_ID": "3U356XVXS2",
            "APNS_TEAM_ID": "89X576BZBF",
            "APNS_TOPIC": "com.paytaca.app",
        },
    )
    assert apns["APNS_USE_SANDBOX"] is False
    assert apns["APNS_AUTH_KEY_PATH"] == "/code/compose/APNS_AuthKey.p8"
    assert apns["APNS_AUTH_KEY_ID"] == "3U356XVXS2"


def test_chipnet_uses_sandbox_host_with_a_separate_key(monkeypatch):
    """Chipnet/dev run with DEBUG=False, so DEBUG cannot pick the endpoint."""
    apns = _build(
        monkeypatch,
        {
            "BCH_NETWORK": "chipnet",
            "APNS_AUTH_KEY_PATH": "/root/dev/AuthKey_sandbox.p8",
            "APNS_AUTH_KEY_ID": "SANDBOXKEY",
            "APNS_TEAM_ID": "89X576BZBF",
        },
    )
    assert apns["APNS_USE_SANDBOX"] is True
    # Absolute paths pass through os.path.join unchanged.
    assert apns["APNS_AUTH_KEY_PATH"] == "/root/dev/AuthKey_sandbox.p8"


def test_unset_credentials_are_omitted_not_inserted_as_none(monkeypatch):
    """`has_auth_token_creds()` treats a present key as configured."""
    apns = _build(monkeypatch, {"BCH_NETWORK": "mainnet"})
    for name in (
        "APNS_AUTH_KEY_PATH",
        "APNS_AUTH_KEY_ID",
        "APNS_TEAM_ID",
        "APNS_TOPIC",
        "APNS_USE_ALTERNATIVE_PORT",
    ):
        assert name not in apns, f"{name} must be absent when unset"
    assert apns["APNS_USE_SANDBOX"] is False


def test_blank_env_values_are_omitted(monkeypatch):
    """An `APNS_AUTH_KEY_ID=` template line must not select token auth."""
    apns = _build(
        monkeypatch,
        {
            "BCH_NETWORK": "mainnet",
            "APNS_AUTH_KEY_PATH": "",
            "APNS_AUTH_KEY_ID": "",
            "APNS_TEAM_ID": "",
            "APNS_TOPIC": "",
        },
    )
    assert "APNS_AUTH_KEY_PATH" not in apns
    assert "APNS_AUTH_KEY_ID" not in apns
    assert "APNS_TOPIC" not in apns


def test_blank_sandbox_value_falls_back_to_the_default(monkeypatch):
    """`APNS_USE_SANDBOX=` must not be read as False."""
    apns = _build(monkeypatch, {"BCH_NETWORK": "chipnet", "APNS_USE_SANDBOX": ""})
    assert apns["APNS_USE_SANDBOX"] is True

    apns = _build(monkeypatch, {"BCH_NETWORK": "mainnet", "APNS_USE_SANDBOX": ""})
    assert apns["APNS_USE_SANDBOX"] is False


def test_explicit_sandbox_value_wins(monkeypatch):
    apns = _build(monkeypatch, {"BCH_NETWORK": "mainnet", "APNS_USE_SANDBOX": "true"})
    assert apns["APNS_USE_SANDBOX"] is True

    apns = _build(monkeypatch, {"BCH_NETWORK": "chipnet", "APNS_USE_SANDBOX": "false"})
    assert apns["APNS_USE_SANDBOX"] is False


def test_library_selects_token_auth_only_when_credentials_are_set(monkeypatch):
    """Pin the library's branch choice, not just our dict shape.

    `LegacyConfig.has_auth_token_creds()` keys off *presence*, so the regression
    that mattered was a real `get_manager()` answering `True` with no
    credentials configured. The library snapshots `PUSH_NOTIFICATIONS_SETTINGS`
    at import time, so patch the module reference it actually reads.
    """
    from push_notifications.conf import get_manager
    from push_notifications.conf import legacy

    monkeypatch.setattr(
        legacy,
        "SETTINGS",
        {
            "CONFIG": "push_notifications.conf.LegacyConfig",
            **_build(monkeypatch, {"BCH_NETWORK": "mainnet"}),
        },
    )
    assert get_manager(reload=True).has_auth_token_creds() is False

    monkeypatch.setattr(
        legacy,
        "SETTINGS",
        {
            "CONFIG": "push_notifications.conf.LegacyConfig",
            **_build(
                monkeypatch,
                {
                    "BCH_NETWORK": "mainnet",
                    "APNS_AUTH_KEY_PATH": "compose/APNS_AuthKey.p8",
                    "APNS_AUTH_KEY_ID": "3U356XVXS2",
                    "APNS_TEAM_ID": "89X576BZBF",
                },
            ),
        },
    )
    manager = get_manager(reload=True)
    assert manager.has_auth_token_creds() is True
    assert manager.get_apns_auth_creds(application_id=None) == (
        "/code/compose/APNS_AuthKey.p8",
        "3U356XVXS2",
        "89X576BZBF",
    )


def test_alternative_port_string_false_does_not_select_port_2197(monkeypatch):
    """apns2 tests the flag for truthiness, so "False" would mean 2197."""
    # "False" is falsy, so the key is omitted and the library's own
    # setdefault(False) keeps the port at 443. What must never happen is a
    # truthy leftover string.
    apns = _build(
        monkeypatch, {"BCH_NETWORK": "mainnet", "APNS_USE_ALTERNATIVE_PORT": "False"}
    )
    assert apns.get("APNS_USE_ALTERNATIVE_PORT", False) is False

    apns = _build(
        monkeypatch, {"BCH_NETWORK": "mainnet", "APNS_USE_ALTERNATIVE_PORT": "true"}
    )
    assert apns["APNS_USE_ALTERNATIVE_PORT"] is True

    apns = _build(monkeypatch, {"BCH_NETWORK": "mainnet"})
    assert apns.get("APNS_USE_ALTERNATIVE_PORT", False) is False


def test_invalid_boolean_value_fails_loudly(monkeypatch):
    """Production uses real decouple, which raises on an unparsable bool."""
    with pytest.raises(ValueError):
        _build(monkeypatch, {"BCH_NETWORK": "mainnet", "APNS_USE_SANDBOX": "maybe"})
