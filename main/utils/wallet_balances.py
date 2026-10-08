import json

from django.conf import settings
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Coalesce

from main.models import (
    CashFungibleToken,
    CashNonFungibleToken,
    Transaction,
)
from main.utils.tx_fee import (
    bch_to_satoshi,
    satoshi_to_bch,
    get_tx_fee_sats,
    truncate,
)

import logging
logger = logging.getLogger(__name__)


# The caller supplies a comma-separated list of asset ids. Each one costs a
# separate aggregate query because multi-token aggregation is unreliable on
# psqlextra's PostgresModel manager -- see the note on _get_slp_balance above.
MAX_ASSETS_PER_REQUEST = 20


# ---------------------------------------------------------------------------
# Aggregation primitives.
#
# These used to live in main/views/view_balance.py, but main/utils/ needs them
# too and importing up into views/ from utils/ inverts the layering and makes
# the import order load-bearing. They live here now; view_balance.py imports
# them back so its own behaviour is unchanged.
# ---------------------------------------------------------------------------

def _get_slp_balance(query, multiple_tokens=False):
    qs = Transaction.objects.filter(query)
    if multiple_tokens:
        # TODO: This is not working as expected in PostgresModel manager
        # I created a github issue for this here:
        # https://github.com/SectorLabs/django-postgres-extra/issues/143
        # Multiple tokens balance will be disabled til that issue is resolved
        qs_balance = qs.annotate(
            _token=F('token__tokenid'),
            token_name=F('token__name'),
            token_ticker=F('token__token_ticker'),
            token_type=F('token__token_type')
        ).rename_annotations(
            _token='token_id'
        ).values(
            'token_id',
            'token_name',
            'token_ticker',
            'token_type'
        ).annotate(
            balance=Coalesce(Sum('amount'), 0)
        )
    else:
        qs_balance = qs.aggregate(Sum('amount'))
    return qs_balance


def _get_ct_balance(query, multiple_tokens=False):
    return _get_slp_balance(query, multiple_tokens)


def _get_bch_balance(query, include_token_sats=False, exclude_dust=True):
    # Exclude dust amounts as they're likely to be SLP transactions
    # TODO: Needs another more sure way to exclude SLP transactions
    dust = 546 # / (10 ** 8)
    if include_token_sats:
        if exclude_dust:
            query = query & Q(value__gt=dust)
        # Use select_related to optimize the query
        qs = Transaction.objects.filter(query).select_related('address', 'token')
    else:
        if exclude_dust:
            query = query & Q(value__gt=dust) & Q(token__name__iexact='bch')
        else:
            query = query & Q(token__name__iexact='bch')
        # Use select_related to optimize the token join
        qs = Transaction.objects.filter(query).select_related('address', 'token')

    # Get both count and sum in a single query using annotations
    # This avoids executing the query twice
    qs_annotated = qs.aggregate(
        balance=Coalesce(Sum('value'), 0),
        count=Count('id')
    )
    qs_count = qs_annotated.get('count', 0)
    qs_balance = {'balance': qs_annotated.get('balance', 0)}
    return qs_balance, qs_count


# Cashtoken categories are 64 hex chars, so the id has more slashes in it than
# the "ct/<category>/<txid>/<index>" split suggests. Splitting on the fixed
# prefix and taking the tail handles that.
FT_PREFIX = 'ct/'
NFT_PREFIX = 'ct/'
BCH_ALIASES = ('bch',)


class InvalidAssetId(ValueError):
    """Raised when an asset id cannot be parsed."""


def get_cache_ttl():
    # Same TTL policy as view_balance.Balance
    return 60 if settings.BCH_NETWORK != 'mainnet' else 60 * 5


def parse_asset_id(asset_id: str) -> dict:
    """
    Parse an asset id into a descriptor.

    Accepts:
        bch
        ct/<category>
        ct/<category>/<txid>/<index>
    """
    if not isinstance(asset_id, str):
        raise InvalidAssetId(f'Invalid asset id: {asset_id}')

    value = asset_id.strip()

    if not value:
        raise InvalidAssetId('Asset id cannot be empty')

    if value.lower() in BCH_ALIASES:
        return {'type': 'bch', 'asset_id': 'bch'}

    if value.lower().startswith('slp/'):
        raise InvalidAssetId(
            'SLP assets are no longer supported. Use a CashToken id '
            '(ct/<category>) or "bch".'
        )

    if not value.lower().startswith(FT_PREFIX):
        raise InvalidAssetId(
            f'Invalid asset id: {asset_id}. Expected "bch", "ct/<category>", '
            'or "ct/<category>/<txid>/<index>".'
        )

    parts = value.split('/')

    # ['ct', category, txid, index]
    if len(parts) == 2:
        category = parts[1]
        if not category:
            raise InvalidAssetId(f'Invalid asset id: {asset_id}. Missing category.')
        return {'type': 'ft', 'asset_id': f'ct/{category}', 'category': category}

    if len(parts) == 4:
        category, txid, index = parts[1], parts[2], parts[3]
        if not category or not txid or not index:
            raise InvalidAssetId(f'Invalid asset id: {asset_id}. Incomplete NFT id.')
        try:
            index = int(index)
        except (TypeError, ValueError):
            raise InvalidAssetId(
                f'Invalid asset id: {asset_id}. Index must be an integer.'
            )
        return {
            'type': 'nft',
            'asset_id': f'ct/{category}/{txid}/{index}',
            'category': category,
            'txid': txid,
            'index': index,
        }

    raise InvalidAssetId(
        f'Invalid asset id: {asset_id}. Expected "ct/<category>" or '
        '"ct/<category>/<txid>/<index>".'
    )


def get_bch_balance(wallet) -> dict:
    """
    BCH balance for a wallet, in BCH.

    Unlike view_balance.Balance this is side-effect free: it does not write
    wallet.last_balance_check and never enqueues a rescan.
    """
    cache = settings.REDISKV
    cache_key = f'wallet:balance:bch:{wallet.wallet_hash}'
    cached_data = cache.get(cache_key)

    if cached_data:
        try:
            return json.loads(cached_data)
        except (TypeError, ValueError):
            logger.warning(f'Corrupt balance cache at {cache_key}, recomputing')

    query = Q(wallet=wallet) & Q(spent=False)
    qs_balance, qs_count = _get_bch_balance(query, exclude_dust=False)
    bch_balance = (qs_balance['balance'] or 0) / (10 ** 8)

    spendable_sats = int(bch_to_satoshi(bch_balance)) - get_tx_fee_sats(
        p2pkh_input_count=qs_count
    )
    spendable = satoshi_to_bch(spendable_sats)
    spendable = max(spendable, 0)

    data = {
        'balance': truncate(bch_balance, 8),
        'spendable': truncate(spendable, 8),
        'valid': True,
    }

    cache.set(cache_key, json.dumps(data), ex=get_cache_ttl())

    return data


def get_asset_balance(wallet, asset_id: str) -> dict:
    """
    Balance for a single CashToken asset, already scaled by its decimals.
    """
    descriptor = parse_asset_id(asset_id)
    category = descriptor['category']

    cache = settings.REDISKV
    cache_key = f'wallet:balance:token:{wallet.wallet_hash}:{category}'
    cached_data = cache.get(cache_key)

    if cached_data:
        try:
            return json.loads(cached_data)
        except (TypeError, ValueError):
            logger.warning(f'Corrupt balance cache at {cache_key}, recomputing')

    query = Q(wallet=wallet) & Q(spent=False)

    if descriptor['type'] == 'nft':
        query = (
            query &
            Q(cashtoken_nft__category=category) &
            Q(cashtoken_nft__current_txid=descriptor['txid']) &
            Q(cashtoken_nft__current_index=descriptor['index'])
        )
    else:
        query = query & Q(cashtoken_ft__category=category)

    qs_balance = _get_ct_balance(query, multiple_tokens=False)
    balance = qs_balance['amount__sum'] or 0

    data = {'balance': 0, 'decimals': 0, 'found': False}

    if descriptor['type'] == 'nft':
        token = CashNonFungibleToken.objects.filter(
            category=category,
            current_txid=descriptor['txid'],
            current_index=descriptor['index']
        ).first()
        if token:
            data.update({
                'balance': 1 if balance > 0 else 0,
                'found': True,
                'name': token.get_info().get('name'),
                'symbol': token.get_info().get('symbol'),
                'commitment': token.commitment,
                'capability': token.capability,
            })
    else:
        token = CashFungibleToken.objects.filter(category=category).first()
        if token:
            info = token.get_info() if token.info else {}
            decimals = info.get('decimals') or 0
            data.update({
                'balance': truncate(balance, decimals) if balance > 0 else 0,
                'decimals': decimals,
                'found': True,
                'name': info.get('name'),
                'symbol': info.get('symbol'),
            })

    cache.set(cache_key, json.dumps(data), ex=get_cache_ttl())

    return data


def get_wallet_balances(wallet, asset_ids) -> dict:
    """
    BCH balance plus one entry per requested CashToken asset, in request order.
    """
    asset_ids = list(asset_ids or [])

    if len(asset_ids) > MAX_ASSETS_PER_REQUEST:
        raise InvalidAssetId(
            f'Too many assets requested. Max is {MAX_ASSETS_PER_REQUEST}.'
        )

    # Parse everything up front so a malformed id fails the whole request
    # rather than half-populating the response.
    descriptors = [parse_asset_id(asset_id) for asset_id in asset_ids]

    data = {
        'wallet_hash': wallet.wallet_hash,
        'bch': get_bch_balance(wallet),
        'assets': [],
    }

    for descriptor in descriptors:
        entry = {'asset_id': descriptor['asset_id']}

        if descriptor['type'] == 'bch':
            entry.update(data['bch'])
        else:
            entry.update(get_asset_balance(wallet, descriptor['asset_id']))

        data['assets'].append(entry)

    return data


def parse_assets_param(assets_param: str) -> list:
    """Split a comma-separated assets query param into a list of ids."""
    return [a.strip() for a in (assets_param or '').split(',') if a.strip()]
