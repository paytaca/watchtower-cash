"""Bounded public HTTP requests pinned to validated destinations."""
import ipaddress
import math
import re
import socket
import time
from urllib.parse import urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import ConnectTimeoutError, NewConnectionError
from urllib3.util.connection import create_connection
from urllib3.util import Timeout


MAX_RESPONSE_BYTES = 1024 * 1024
BLOCKED_NETWORKS = tuple(ipaddress.ip_network(value) for value in (
    '192.0.0.0/24', '192.88.99.0/24',
    '64:ff9b::/96', '64:ff9b:1::/48', '2001::/23', '2002::/16',
))


class UnsafePublicURL(requests.exceptions.RequestException):
    pass


UnsafePaymentURL = UnsafePublicURL


def _public_address(value):
    address = ipaddress.ip_address(value)
    if (not address.is_global or address.is_multicast or address.is_reserved
            or address.is_loopback or address.is_link_local or address.is_unspecified
            or getattr(address, 'ipv4_mapped', None) is not None
            or any(address.version == network.version and address in network
                   for network in BLOCKED_NETWORKS)):
        raise UnsafePublicURL('URLs must resolve only to public IP addresses.')
    return str(address)


def _destination(url):
    if (not isinstance(url, str) or not url or len(url) > 2048
            or '\\' in url or any(ord(char) <= 32 or ord(char) == 127 for char in url)):
        raise UnsafePublicURL('A valid public HTTP(S) URL is required.')
    try:
        parsed = urlsplit(url)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname
                or parsed.username is not None or parsed.password is not None):
            raise ValueError
        host = parsed.hostname.rstrip('.').encode('idna').decode('ascii').lower()
        port = parsed.port if parsed.port is not None else (443 if parsed.scheme == 'https' else 80)
        if port != (443 if parsed.scheme == 'https' else 80) or '%' in host:
            raise ValueError
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            literal = None
            if not re.fullmatch(r'[a-z0-9.-]+', host) or len(host) > 253:
                raise ValueError
        if literal is not None:
            addresses = [_public_address(host)]
        else:
            answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            addresses = []
            for family, _, _, _, sockaddr in answers:
                if family not in (socket.AF_INET, socket.AF_INET6):
                    raise ValueError
                address = _public_address(sockaddr[0])
                if address not in addresses:
                    addresses.append(address)
            if not addresses:
                raise ValueError
        authority = '[{}]'.format(host) if ':' in host else host
        normalized = urlunsplit((parsed.scheme, authority, parsed.path or '/', parsed.query, ''))
        return normalized, parsed.scheme, host, port, tuple(addresses)
    except UnsafePublicURL:
        raise
    except OSError as err:
        raise requests.exceptions.ConnectionError('Public URL resolution failed.') from err
    except (ValueError, UnicodeError) as err:
        raise UnsafePublicURL('A resolvable public HTTP(S) URL is required.') from err


def validate_public_http_url(url):
    _destination(url)
    return url


class _PinnedConnection:
    def __init__(self, *args, pinned_addresses, **kwargs):
        self._pinned_addresses = pinned_addresses
        super().__init__(*args, **kwargs)

    def _new_conn(self):
        # Keep self.host unchanged for Host headers, SNI and certificate checks.
        timeout = self.timeout
        if isinstance(timeout, Timeout):
            timeout = timeout.connect_timeout
        if timeout is None or timeout is socket._GLOBAL_DEFAULT_TIMEOUT:
            timeout = socket.getdefaulttimeout()
        # urllib3 versions use different default sentinels. Always retain a
        # finite connection budget, including for unset or unbounded defaults.
        if (not isinstance(timeout, (int, float)) or isinstance(timeout, bool)
                or not math.isfinite(timeout) or timeout <= 0):
            timeout = 5
        deadline = time.monotonic() + timeout
        last_error = None
        for address in self._pinned_addresses:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ConnectTimeoutError(self, 'Public HTTP connection timed out.')
            try:
                return create_connection(
                    (address, self.port), remaining,
                    source_address=self.source_address, socket_options=self.socket_options,
                )
            except OSError as err:
                last_error = err
        if isinstance(last_error, socket.timeout):
            raise ConnectTimeoutError(self, 'Public HTTP connection timed out.') from last_error
        raise NewConnectionError(self, 'Public HTTP connection failed.') from last_error


class _PinnedHTTPConnection(_PinnedConnection, HTTPConnection):
    pass


class _PinnedHTTPSConnection(_PinnedConnection, HTTPSConnection):
    pass


class _PinnedHTTPPool(HTTPConnectionPool):
    ConnectionCls = _PinnedHTTPConnection


class _PinnedHTTPSPool(HTTPSConnectionPool):
    ConnectionCls = _PinnedHTTPSConnection


class _PaymentAdapter(HTTPAdapter):
    def __init__(self, scheme, host, port, addresses):
        super().__init__(max_retries=0)
        self._origin = (scheme, host, port)
        pool = _PinnedHTTPSPool if scheme == 'https' else _PinnedHTTPPool
        self._pool = pool(host, port, pinned_addresses=addresses)

    def get_connection(self, url, proxies=None):
        parsed = urlsplit(url)
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        if proxies or (parsed.scheme, parsed.hostname, port) != self._origin:
            raise UnsafePublicURL('Public HTTP connection destination changed.')
        return self._pool

    def get_connection_with_tls_context(self, request, verify, proxies=None, cert=None):
        # requests 2.32+ resolves the TLS context here; older versions call
        # cert_verify() from send(). Apply it explicitly so every supported
        # requests version honors a custom CA bundle or client certificate.
        conn = self.get_connection(request.url, proxies=proxies)
        self.cert_verify(conn, request.url, verify, cert)
        return conn

    def close(self):
        self._pool.close()
        super().close()


class _PaymentSession(requests.Session):
    def resolve_redirects(self, *args, **kwargs):
        # Requests otherwise consumes redirect bodies to prepare Response.next,
        # even with allow_redirects=False, before our response-size check runs.
        return iter(())


def public_request(method, url, *, headers=None, data=None, verify=True):
    if method not in ('GET', 'POST'):
        raise ValueError('Unsupported public HTTP method.')
    if verify is not True and (not isinstance(verify, str) or not verify):
        raise ValueError('TLS certificate verification is required.')
    url, scheme, host, port, addresses = _destination(url)
    deadline = time.monotonic() + 30
    with _PaymentSession() as session:
        # Ignore proxy variables and .netrc credentials from the environment.
        session.trust_env = False
        session.mount(scheme + '://', _PaymentAdapter(scheme, host, port, addresses))
        with session.request(
            method, url, headers=headers, data=data, verify=verify,
            timeout=(5, 10), allow_redirects=False, stream=True,
        ) as response:
            if 300 <= response.status_code < 400:
                raise UnsafePublicURL('URL redirects are not supported; use the final public URL.')
            chunks = []
            size = 0
            for chunk in response.iter_content(chunk_size=8192):
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise UnsafePublicURL('Public HTTP response exceeds the size limit.')
                if time.monotonic() > deadline:
                    raise requests.exceptions.Timeout('Public HTTP response timed out.')
                chunks.append(chunk)
            response._content = b''.join(chunks)
            response._content_consumed = True
            return response


payment_request = public_request
