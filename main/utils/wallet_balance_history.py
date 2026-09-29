import logging
from decimal import Decimal

import pytz

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, Sum, Max
from django.db.models.functions import Coalesce
from django.utils import timezone

from main.models import Wallet, WalletHistory, Address, Transaction

logger = logging.getLogger(__name__)

DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100
DEFAULT_TIMEZONE = 'Asia/Manila'


def format_amount(amount, decimals=8):
    """Format an amount with thousands separators and fixed decimals.

    Truncates (does not round) to `decimals` places, e.g.
    1000.84 with 8 decimals -> '1,000.84000000'.
    """
    if amount is None:
        return None
    decimals = max(int(decimals or 0), 0)
    try:
        quantized = Decimal(str(amount)).quantize(
            Decimal(1).scaleb(-decimals), rounding='ROUND_DOWN')
    except Exception:
        return str(amount)
    return '{:,.{decimals}f}'.format(quantized, decimals=decimals)


def convert_to_timezone(dt, tz_name):
    """Convert a datetime to the named timezone; None-safe.

    Naive datetimes are assumed to be UTC.
    """
    if not dt:
        return None
    try:
        tz = pytz.timezone(tz_name)
    except (pytz.UnknownTimeZoneError, AttributeError, TypeError):
        return dt
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, pytz.utc)
    return dt.astimezone(tz)


def format_timestamp(dt, tz_name=None, fmt='%Y-%m-%d %H:%M:%S %Z'):
    """Render a datetime in the requested timezone as a display string."""
    if not dt:
        return None
    converted = convert_to_timezone(dt, tz_name)
    if converted is None:
        return None
    return converted.strftime(fmt)


def generate_reference_id(txid):
    """Derive the 8-digit decimal reference ID used by Paytaca apps.

    Reference ID = first 6 hex chars of the txid parsed as an integer,
    zero-padded to 8 decimal digits.
    """
    if not txid or len(txid) < 6:
        return None
    try:
        return str(int(txid[:6], 16)).zfill(8)
    except ValueError:
        return None


def _relative_time(dt):
    if not dt:
        return None
    delta = timezone.now() - dt
    seconds = int(delta.total_seconds())
    if seconds < 0:
        seconds = 0
    intervals = [
        (31536000, 'year'),
        (2592000, 'month'),
        (86400, 'day'),
        (3600, 'hour'),
        (60, 'minute'),
        (1, 'second'),
    ]
    for seconds_in_unit, unit in intervals:
        if seconds >= seconds_in_unit:
            count = int(seconds // seconds_in_unit)
            return f'{count} {unit}{"s" if count != 1 else ""} ago'
    return 'just now'


def get_wallet_balance_history(wallet_hash, fiat_currency='PHP', page=1,
                               per_page=DEFAULT_PER_PAGE, date_timezone=DEFAULT_TIMEZONE):
    """Build wallet balance + paginated history data.

    Returns (wallet_data, error). On error, wallet_data is None and error
    contains the message.
    """
    from main.utils.tx_fee import get_tx_fee_sats, bch_to_satoshi, satoshi_to_bch
    from main.tasks import get_latest_bch_price

    try:
        wallet = Wallet.objects.get(wallet_hash=wallet_hash)
    except Wallet.DoesNotExist:
        return None, f'Wallet not found: {wallet_hash}'

    wallet_data = {
        'wallet_hash': wallet.wallet_hash,
        'wallet_type': wallet.wallet_type,
        'project': str(wallet.project) if wallet.project else None,
        'date_created': wallet.date_created,
        'last_balance_check': wallet.last_balance_check,
        'last_balance_check_relative': _relative_time(wallet.last_balance_check),
        'last_utxo_scan_succeeded': wallet.last_utxo_scan_succeeded,
        'fiat_currency': fiat_currency,
        'date_timezone': date_timezone,
        'date_created_display': format_timestamp(wallet.date_created, date_timezone),
        'last_balance_check_display': format_timestamp(wallet.last_balance_check, date_timezone),
    }

    # Get latest subscribed address pair
    addresses = Address.objects.filter(wallet=wallet).values_list('address_path', flat=True)
    max_index = None
    for addr_path in addresses:
        if addr_path and '/' in addr_path:
            try:
                _, idx = addr_path.split('/')
                idx = int(idx)
                if max_index is None or idx > max_index:
                    max_index = idx
            except (ValueError, IndexError):
                continue

    if max_index is not None:
        receiving_path = f'0/{max_index}'
        change_path = f'1/{max_index}'
        receiving_addr = Address.objects.filter(wallet=wallet, address_path=receiving_path).first()
        change_addr = Address.objects.filter(wallet=wallet, address_path=change_path).first()
        wallet_data['latest_address_pair'] = {
            'index': max_index,
            'receiving': receiving_addr.address if receiving_addr else None,
            'change': change_addr.address if change_addr else None,
        }

    # Get BCH balance
    if wallet.wallet_type == 'bch':
        query = Q(wallet=wallet) & Q(spent=False) & Q(token__name__iexact='bch')
        qs_balance = Transaction.objects.filter(query).aggregate(
            balance=Coalesce(Sum('value'), 0)
        )
        bch_balance = (qs_balance['balance'] or 0) / (10 ** 8)
        qs_count = Transaction.objects.filter(query).count()

        spendable = int(bch_to_satoshi(bch_balance)) - get_tx_fee_sats(p2pkh_input_count=qs_count)
        spendable = satoshi_to_bch(spendable)
        spendable = max(spendable, 0)

        wallet_data['bch_balance'] = round(bch_balance, 8)
        wallet_data['bch_spendable'] = round(spendable, 8)
        wallet_data['bch_utxo_count'] = qs_count

        # Get current fiat price for balance conversion
        current_price_log = get_latest_bch_price(fiat_currency)
        if current_price_log:
            current_fiat_price = float(current_price_log.price_value)
            wallet_data['current_fiat_price'] = current_fiat_price
            wallet_data['bch_fiat_balance'] = round(bch_balance * current_fiat_price, 2)
            wallet_data['bch_fiat_spendable'] = round(spendable * current_fiat_price, 2)
        else:
            wallet_data['current_fiat_price'] = None
            wallet_data['bch_fiat_balance'] = None
            wallet_data['bch_fiat_spendable'] = None

        # Get token balances
        from collections import defaultdict
        token_balances = []
        token_query = Q(wallet=wallet) & Q(spent=False) & Q(cashtoken_ft__isnull=False)
        token_transactions = Transaction.objects.filter(token_query).select_related('cashtoken_ft', 'cashtoken_ft__info')

        token_groups = defaultdict(lambda: {'amount': 0, 'info': None})

        for tx in token_transactions:
            if tx.cashtoken_ft:
                category = tx.cashtoken_ft.category
                token_groups[category]['amount'] += tx.amount
                if not token_groups[category]['info'] and tx.cashtoken_ft.info:
                    token_groups[category]['info'] = {
                        'name': tx.cashtoken_ft.info.name,
                        'symbol': tx.cashtoken_ft.info.symbol,
                        'decimals': tx.cashtoken_ft.info.decimals,
                    }

        for category, data in token_groups.items():
            decimals = data['info']['decimals'] if data['info'] else 0
            balance = round(data['amount'], decimals)
            token_balances.append({
                'category': category,
                'balance': balance,
                'balance_display': format_amount(balance, decimals),
                'name': data['info']['name'] if data['info'] else 'Unknown',
                'symbol': (data['info']['symbol'] if data['info'] else 'N/A').upper(),
                'decimals': decimals,
            })

        wallet_data['token_balances'] = token_balances

        # Sum BCH locked in CashToken UTXOs (diagnostic)
        cashtoken_bch_query = Q(wallet=wallet) & Q(spent=False) & Q(cashtoken_ft__isnull=False)
        cashtoken_bch_balance = Transaction.objects.filter(cashtoken_bch_query).aggregate(
            total=Coalesce(Sum('value'), 0)
        )['total'] or 0
        wallet_data['cashtoken_locked_bch'] = round(cashtoken_bch_balance / (10 ** 8), 8)

    # Get paginated wallet history
    history_qs = WalletHistory.objects.filter(wallet=wallet).exclude(amount=0).order_by(
        '-tx_timestamp', '-date_created'
    ).select_related('token', 'cashtoken_ft', 'cashtoken_nft')

    per_page = min(max(int(per_page or DEFAULT_PER_PAGE), 1), MAX_PER_PAGE)
    paginator = Paginator(history_qs, per_page)
    try:
        history_page = paginator.page(page)
    except PageNotAnInteger:
        history_page = paginator.page(1)
    except EmptyPage:
        history_page = paginator.page(paginator.num_pages)

    history_list = []
    for record in history_page.object_list:
        # Get fiat price at time of transaction
        record_fiat_price = None
        if record.market_prices and record.market_prices.get(fiat_currency):
            record_fiat_price = record.market_prices[fiat_currency]
        elif fiat_currency == 'USD' and record.usd_price:
            record_fiat_price = float(record.usd_price)

        # Determine asset label (uppercase ticker) and display decimals.
        # BCH records store amounts in BCH (8 decimals); CashToken records
        # store amounts in base units, divided by 10^decimals.
        if record.cashtoken_ft:
            info = record.cashtoken_ft.info
            token_name = (info.symbol or info.name or 'N/A') if info else 'N/A'
            decimals = info.decimals if (info and info.decimals is not None) else 0
            display_amount = record.amount / (10 ** decimals)
        elif record.cashtoken_nft:
            info = record.cashtoken_nft.info
            token_name = (info.symbol or info.name or 'N/A') if info else 'N/A'
            decimals = 0
            display_amount = record.amount
        elif record.token:
            token_name = record.token.token_ticker or record.token.name or 'bch'
            decimals = record.token.decimals if record.token.decimals is not None else 8
            display_amount = record.amount
        else:
            token_name = 'BCH'
            decimals = 8
            display_amount = record.amount

        display_timestamp = format_timestamp(record.tx_timestamp or record.date_created, date_timezone)

        history_list.append({
            'id': record.id,
            'txid': record.txid,
            'reference_id': generate_reference_id(record.txid),
            'record_type': record.record_type,
            'amount': record.amount,
            'display_amount': format_amount(display_amount, decimals),
            'decimals': decimals,
            'tx_fee': record.tx_fee,
            'tx_timestamp': record.tx_timestamp,
            'date_created': record.date_created,
            'display_timestamp': display_timestamp,
            'token_name': token_name.upper() if token_name else None,
            'cashtoken_category': record.cashtoken_ft.category if record.cashtoken_ft else None,
            'usd_price': float(record.usd_price) if record.usd_price else None,
            'fiat_price': float(record_fiat_price) if record_fiat_price else None,
            'fiat_value': round(float(record_fiat_price) * record.amount, 2) if record_fiat_price else None,
        })

    wallet_data['history'] = history_list
    wallet_data['history_count'] = len(history_list)
    wallet_data['total_history_count'] = paginator.count
    wallet_data['has_fiat_prices'] = any(record.get('fiat_price') for record in history_list)

    wallet_data['pagination'] = {
        'page': history_page.number,
        'per_page': per_page,
        'num_pages': paginator.num_pages,
        'total': paginator.count,
        'has_previous': history_page.has_previous(),
        'has_next': history_page.has_next(),
        'previous_page': history_page.previous_page_number() if history_page.has_previous() else None,
        'next_page': history_page.next_page_number() if history_page.has_next() else None,
        'page_range': _page_range(history_page.number, paginator.num_pages),
    }

    return wallet_data, None


def _page_range(current, num_pages, window=2):
    """Return a compact list of page numbers with None as an ellipsis marker."""
    pages = set()
    pages.update(range(1, min(window + 1, num_pages) + 1))
    pages.update(range(max(1, current - window), min(num_pages, current + window) + 1))
    pages.update(range(max(1, num_pages - window), num_pages + 1))
    ordered = sorted(pages)
    result = []
    prev = None
    for p in ordered:
        if prev is not None and p - prev > 1:
            result.append(None)
        result.append(p)
        prev = p
    return result
