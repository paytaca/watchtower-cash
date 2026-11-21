"""Authenticated loopback-only clients; never send service tokens via proxies."""
import re

from decouple import config
from django.core.exceptions import ImproperlyConfigured
import requests

_SERVICES = {
    'stablehedge': ('STABLEHEDGE_JS_AUTH_TOKEN', 'http://127.0.0.1:3010/'),
    'address': ('ADDRESS_JS_AUTH_TOKEN', 'http://127.0.0.1:3000/'),
    'cts': ('CTS_JS_AUTH_TOKEN', 'http://127.0.0.1:3001/'),
    'multisig': ('MULTISIG_JS_AUTH_TOKEN', 'http://127.0.0.1:3004/'),
    'anyhedge': ('ANYHEDGE_JS_AUTH_TOKEN', 'http://127.0.0.1:3020/'),
}


def service_request(service, method, path='/', timeout=30, **kwargs):
    name, base_url = _SERVICES[service]
    if method not in ('GET', 'POST') or not path.startswith('/') or path.startswith('//'):
        raise ValueError('Expected GET/POST and an absolute path on the internal service')
    url = base_url + path[1:]
    token = config(name, default='')
    if not re.fullmatch(r'[A-Za-z0-9_-]{43,}', token) or len(set(token)) < 5:
        raise ImproperlyConfigured(
            '{} must be set to a randomly generated URL-safe token of at least 43 characters'.format(name)
        )
    with requests.Session() as session:
        session.trust_env = False
        return getattr(session, method.lower())(
            url, headers={'Authorization': 'Bearer ' + token},
            timeout=timeout, allow_redirects=False, **kwargs,
        )


def post_script_request(service, payload):
    return service_request(service, 'POST', json=payload)
