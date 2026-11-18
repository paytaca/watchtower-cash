"""Build the APNs portion of `PUSH_NOTIFICATIONS_SETTINGS` from the environment.

Kept out of `watchtower/settings.py` so the rules here can be unit tested
without importing the whole settings module (which pulls in every app).

Two `django-push-notifications` behaviours drive this code:

* Token auth is selected on key *presence*. `LegacyConfig.has_auth_token_creds()`
  runs `SETTINGS.get(key, empty)` for the key path, key id and team id, so a key
  present with `None` or `""` still counts as configured. Inserting unset keys
  therefore selects token auth with blank credentials instead of failing clearly.
* `APNS_USE_SANDBOX` only defaults from `DEBUG` when the key is absent, which is
  the wrong signal here: chipnet and dev run with `DEBUG=False` but must talk to
  the sandbox host, and a sandbox p8 key is rejected by the production host with
  `BadEnvironmentKeyInToken`. The p8 key does not select the endpoint, so the
  deployment target has to.
"""
import os

from decouple import config


def _path(base_dir, setting_name):
    """Resolve a credential path against `base_dir`, or None when unset."""
    path = config(setting_name, None)
    if not path:
        return None
    return os.path.join(base_dir, path)


def _bool(setting_name, default):
    """Bool setting where a blank env value means "unset", not False.

    `django-decouple` passes `""` straight to `bool()`, so a template line like
    `APNS_USE_SANDBOX=` would otherwise silently disable sandbox mode.
    """
    value = config(setting_name, None)
    if value is None or value == "":
        return default
    return config(setting_name, cast=bool)


def build_apns_settings(base_dir):
    """Return the APNs keys to merge into `PUSH_NOTIFICATIONS_SETTINGS`.

    Unset values are omitted rather than inserted as `None`/`""`, so the
    library's presence checks match the deployment's actual configuration.
    """
    apns = {
        # The p8 key does not pick the endpoint; follow the chain unless the
        # environment says otherwise.
        "APNS_USE_SANDBOX": _bool(
            "APNS_USE_SANDBOX", config("BCH_NETWORK", default="chipnet") != "mainnet"
        ),
    }

    configured = (
        ("APNS_AUTH_KEY_PATH", _path(base_dir, "APNS_AUTH_KEY_PATH")),
        ("APNS_AUTH_KEY_ID", config("APNS_AUTH_KEY_ID", None)),
        ("APNS_TEAM_ID", config("APNS_TEAM_ID", None)),
        ("APNS_TOPIC", config("APNS_TOPIC", None)),
        # Not a raw string: apns2 does `ALTERNATIVE_PORT if use_alternative_port
        # else DEFAULT_PORT`, so `APNS_USE_ALTERNATIVE_PORT=False` would be a
        # truthy string and send to 2197 instead of 443.
        ("APNS_USE_ALTERNATIVE_PORT", _bool("APNS_USE_ALTERNATIVE_PORT", False)),
    )
    for name, value in configured:
        if value:
            apns[name] = value

    return apns
