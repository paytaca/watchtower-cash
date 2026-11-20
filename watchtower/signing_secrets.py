"""Validate deployment-supplied signing keys without logging their values."""
import hashlib

from django.core.exceptions import ImproperlyConfigured


# Fingerprint of the previously published key; never accept it from configuration.
_EXPOSED_KEY_SHA256 = "0234a9b9d9ea8157845d3dc1bb8aadb937de1ea71f9c7589f155d6c3fdfceb2b"


def require_signing_secret(config, name):
    value = config(name, default="")
    if (
        not isinstance(value, str)
        or len(value.strip()) < 50
        or len(set(value)) < 5
        or hashlib.sha256(value.strip().encode()).hexdigest() == _EXPOSED_KEY_SHA256
    ):
        raise ImproperlyConfigured(
            "{} must be set to a new, randomly generated secret of at least "
            "50 characters; the previously published key is forbidden.".format(name)
        )
    return value
