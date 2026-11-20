"""Authenticated loopback-only clients; never send service tokens via proxies."""
import re

from decouple import config
from django.core.exceptions import ImproperlyConfigured
import requests

_SERVICES = {
    'stablehedge': ('STABLEHEDGE_JS_AUTH_TOKEN', 'http://127.0.0.1:3010/'),
    'anyhedge': ('ANYHEDGE_JS_AUTH_TOKEN', 'http://127.0.0.1:3020/'),
}


def post_script_request(service, payload):
    name, url = _SERVICES[service]
    token = config(name, default='')
    if not re.fullmatch(r'[A-Za-z0-9_-]{43,}', token) or len(set(token)) < 5:
        raise ImproperlyConfigured(
            '{} must be set to a randomly generated URL-safe token of at least 43 characters'.format(name)
        )
    with requests.Session() as session:
        session.trust_env = False
        return session.post(
            url, json=payload, headers={'Authorization': 'Bearer ' + token},
            timeout=30, allow_redirects=False,
        )
