"""Authenticated requests to the private CTS helper."""
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

from internal_services.client import service_request


def _token_authguard_address(category):
    response = service_request(
        'cts', 'GET',
        '/cts/js/authguard-token-deposit-address/' + quote(category, safe=''),
    )
    response.raise_for_status()
    return response.json()


def get_token_authguard_addresses(categories):
    # Propagate failures to the caller instead of silently returning partial data
    # when a background thread encounters an authentication or connection error.
    with ThreadPoolExecutor(max_workers=8) as executor:
        return list(executor.map(_token_authguard_address, categories))
