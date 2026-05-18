import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def fetch_bcmr_raw(category, commitment=None, timeout=None):
    """
    Fetch raw metadata from the BCMR indexer for a cashtoken category (and optional commitment).
    Returns the parsed JSON dict on success.
    Returns a dict with an 'error' key on failure (timeout, HTTP error, invalid JSON, or API error).
    """
    url = f'{settings.PAYTACA_BCMR_URL}/tokens/{category}/'
    if commitment:
        url = f'{url}{commitment}/'

    try:
        response = requests.get(url, timeout=timeout)
    except (requests.Timeout, requests.RequestException) as e:
        logger.warning(f'Timeout or error fetching metadata for cashtoken {category}: {str(e)}')
        return dict(error=str(e), timeout=True, transport_error=True)

    if response.status_code != 200:
        return dict(error=f'HTTP {response.status_code}', status_code=response.status_code, http_error=True)

    try:
        data = response.json()
    except ValueError:
        return dict(error='Invalid JSON response', parse_error=True)

    if 'error' in data:
        return dict(error=data['error'], api_error=True)

    return data


def _truncate(value, max_length):
    """Truncate a string value to a safe length."""
    if value and len(value) > max_length:
        return value[:max_length]
    return value


def parse_bcmr_to_info(data, is_nft=False, category=None, capability=None):
    """
    Extract and normalize token metadata from a BCMR JSON response for storage in CashTokenInfo.

    Parameters
    ----------
    data : dict
        The raw BCMR JSON response.
    is_nft : bool
        Whether to extract NFT-specific fields (type_metadata priority) or FT fields.
    category : str, optional
        Used to build a fallback name like "CT-xxxx".
    capability: str, optional
        Used as condition for `nft_details` population

    Returns
    -------
    dict or None
        A dict with keys: name, description, symbol, decimals, image_url.
        nft_details is also included for minting nft types
        Returns None if the input data is missing or contains an error.
    """
    if not data or 'error' in data:
        return None

    fallback_name = f'CT-{category[:4]}' if category else 'CashToken'

    if is_nft:
        type_metadata = data.get('type_metadata', {})
        name = type_metadata.get('name') or data.get('name') or fallback_name
        symbol = data.get('token', {}).get('symbol', '')
        description = type_metadata.get('description') or data.get('description', '')
        type_metadata_uris = type_metadata.get('uris', {})
        token_uris = data.get('uris', {})
        image_url = type_metadata_uris.get('image') or type_metadata.get('icon') or token_uris.get('icon')
        try:
            decimals = int(data.get('token', {}).get('decimals'))
        except (TypeError, ValueError):
            decimals = None

    else:
        name = data.get('name') or fallback_name
        symbol = data.get('token', {}).get('symbol', '')
        description = data.get('description', '')
        uris = data.get('token', {}).get('uris')
        if not uris:
            uris = data.get('uris') or {'icon': None}
        image_url = uris.get('icon')
        try:
            decimals = int(data.get('token', {}).get('decimals'))
        except (TypeError, ValueError):
            decimals = 0

    result = {
        'name': _truncate(name, 200),
        'description': _truncate(description, 1000),
        'symbol': _truncate(symbol, 100),
        'decimals': decimals,
        'image_url': _truncate(image_url, 200),
    }

    # Kept existing logic for populating nft_details from previous implementation of `get_cashtoken_meta_data` however
    # unable to find tokens that cover this case
    if isinstance(capability, str) and capability.lower() == "minting" and data.get('types'):
        result['nft_details'] = data.get('types')

    return result
