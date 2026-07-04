import base64
import datetime
import pickle
import math

from django.conf import settings
from django.db.models import F, Q

from main.models import Transaction, WalletHistory, Wallet
from main.utils.address_validator import is_bch_address


def clear_transaction_cache(transaction_instance):
    """
    Utility function to clear cache for a transaction.
    This can be called when transactions are updated using .update() 
    which doesn't trigger Django signals.
    """
    cache = settings.REDISKV
    
    # Clear address balance cache if address exists
    if transaction_instance.address:
        address = transaction_instance.address.address
        if is_bch_address(address):
            # Invalidate both variants of the address balance cache key
            cache_key_false = f'address:balance:bch:{address}:False'
            cache_key_true = f'address:balance:bch:{address}:True'
            cache.delete(cache_key_false)
            cache.delete(cache_key_true)
    
    # Clear wallet balance cache if wallet exists
    if transaction_instance.address and transaction_instance.address.wallet:
        wallet_hash = transaction_instance.address.wallet.wallet_hash
        
        # delete cached bch balance
        bch_cache_key = f'wallet:balance:bch:{wallet_hash}'
        cache.delete(bch_cache_key)
        
        # delete cached token balance
        category = None
        if transaction_instance.cashtoken_ft:
            category = transaction_instance.cashtoken_ft.category
        elif transaction_instance.spent and transaction_instance.spending_txid:
            # This is a spent input, try to get the category from the output
            spent_tx = Transaction.objects.filter(txid=transaction_instance.txid, index=transaction_instance.index).first()
            if spent_tx and spent_tx.cashtoken_ft:
                category = spent_tx.cashtoken_ft.category
        
        if category:
            ct_cache_key = f'wallet:balance:token:{wallet_hash}:{category}'
            cache.delete(ct_cache_key)
        
        # delete cached wallet history
        asset_key = category or 'bch'
        history_cache_keys = cache.keys(f'wallet:history:{wallet_hash}:{asset_key}:*')
        if history_cache_keys:
            cache.delete(*history_cache_keys)
        
        # Clear last address index cache since an address has received a transaction
        # This affects the "with_tx" variant of the last address index endpoint
        clear_last_address_index_cache(wallet_hash)


def clear_cache_for_spent_transactions(transaction_queryset):
    """
    Clear cache for multiple transactions that are being marked as spent.
    This is more efficient than calling clear_transaction_cache for each transaction.
    Clears both address and wallet balance caches.
    """
    if not transaction_queryset.exists():
        return
    
    # Get unique addresses, wallet hashes and categories from the transactions
    addresses = set()
    wallet_hashes = set()
    categories = set()
    
    for txn in transaction_queryset.select_related('address__wallet', 'cashtoken_ft'):
        if txn.address:
            addresses.add(txn.address.address)
            
            if txn.address.wallet:
                wallet_hashes.add(txn.address.wallet.wallet_hash)
            
            if txn.cashtoken_ft:
                categories.add(txn.cashtoken_ft.category)
            elif txn.spent and txn.spending_txid:
                # This is a spent input, try to get the category from the output
                spent_tx = Transaction.objects.filter(txid=txn.txid, index=txn.index).first()
                if spent_tx and spent_tx.cashtoken_ft:
                    categories.add(spent_tx.cashtoken_ft.category)
    
    cache = settings.REDISKV
    
    # Clear address balance cache for all affected addresses
    for address in addresses:
        if is_bch_address(address):
            # Invalidate both variants of the address balance cache key
            cache_key_false = f'address:balance:bch:{address}:False'
            cache_key_true = f'address:balance:bch:{address}:True'
            cache.delete(cache_key_false)
            cache.delete(cache_key_true)
    
    # Clear BCH balance cache for all affected wallets
    for wallet_hash in wallet_hashes:
        bch_cache_key = f'wallet:balance:bch:{wallet_hash}'
        cache.delete(bch_cache_key)
        
        # Clear token balance cache for all affected categories
        for category in categories:
            ct_cache_key = f'wallet:balance:token:{wallet_hash}:{category}'
            cache.delete(ct_cache_key)
        
        # Clear wallet history cache
        history_cache_keys = cache.keys(f'wallet:history:{wallet_hash}:*')
        if history_cache_keys:
            cache.delete(*history_cache_keys)
        
        # Clear last address index cache since addresses received transactions
        clear_last_address_index_cache(wallet_hash) 


def clear_wallet_balance_cache(wallet_hash, token_categories=None):
    """
    Clear wallet balance cache for a given wallet hash.
    Always clears BCH balance cache.
    If token_categories is provided (list/set), clears token balance cache for those categories.
    If token_categories is None, clears all token balance caches for the wallet.
    """
    if not wallet_hash:
        return
    
    cache = settings.REDISKV
    
    # Always clear BCH balance
    bch_cache_key = f'wallet:balance:bch:{wallet_hash}'
    cache.delete(bch_cache_key)
    
    # Clear token balance cache
    if token_categories is None:
        # Clear all token balance caches for this wallet
        token_cache_keys = cache.keys(f'wallet:balance:token:{wallet_hash}:*')
        if token_cache_keys:
            cache.delete(*token_cache_keys)
    elif token_categories:
        # Clear only specific token categories
        for category in token_categories:
            if category:  # Skip None/empty categories
                token_cache_key = f'wallet:balance:token:{wallet_hash}:{category}'
                cache.delete(token_cache_key)


def clear_wallet_history_cache(wallet_hash, asset_key=None):
    """
    Clear wallet history cache for a given wallet hash.
    If asset_key is provided, only clears cache for that specific asset.
    If asset_key is None, clears all history cache for the wallet.
    """
    if not wallet_hash:
        return
    
    cache = settings.REDISKV
    
    if asset_key:
        # Clear cache for specific asset (all pages)
        history_cache_keys = cache.keys(f'wallet:history:{wallet_hash}:{asset_key}:*')
    else:
        # Clear all history cache for the wallet (all assets, all pages)
        history_cache_keys = cache.keys(f'wallet:history:{wallet_hash}:*')
    
    if history_cache_keys:
        cache.delete(*history_cache_keys)


def clear_pos_wallet_history_cache(wallet_hash, posid):
    """Invalidate cached POS wallet history responses for a specific POS ID."""
    if posid is None:
        return

    cache = settings.REDISKV

    pos_history_cache_keys = cache.keys(f'wallet:history:{wallet_hash}:pos:*')
    if not pos_history_cache_keys:
        return

    target_posid = str(posid)

    for cache_key in pos_history_cache_keys:
        # Redis may return bytes keys; normalise to str for parsing
        if isinstance(cache_key, bytes):
            try:
                decoded_key = cache_key.decode('utf-8')
            except UnicodeDecodeError:
                continue
        else:
            decoded_key = cache_key

        if ':pos:' not in decoded_key:
            continue

        encoded_params = decoded_key.split(':pos:', 1)[1]

        try:
            request_params = pickle.loads(base64.b64decode(encoded_params))
        except Exception:
            # Skip keys we cannot decode safely
            continue

        request_posid = request_params.get('posid')
        if request_posid is None:
            continue

        if str(request_posid) != target_posid:
            continue

        # Delete cached response and corresponding count entry
        cache.delete(cache_key)
        cache.delete(f"{decoded_key}:count")


def clear_last_address_index_cache(wallet_hash):
    """
    Clear the last address index cache for a given wallet hash.
    This should be called when addresses are created or updated.
    
    Performance Note: Uses Redis KEYS command which can be slow on large datasets.
    However, this is acceptable because:
    1. Cache key pattern is highly specific (wallet_hash scoped)
    2. Typically returns at most 8-16 keys (4 boolean combinations × 2-4 posid variants)
    3. Called infrequently (only when addresses are added/updated)
    
    Future optimization: If this becomes a bottleneck, consider:
    - Using Redis SCAN instead of KEYS
    - Maintaining a Redis SET of cache keys per wallet for faster lookup
    - Using Redis Hash with HGETALL/HDEL for grouped invalidation
    """
    if not wallet_hash:
        return
    
    cache = settings.REDISKV
    
    # Clear all variations of last address index cache for this wallet
    # The cache key pattern is: wallet:last_address_index:{wallet_hash}:{with_tx}:{exclude_pos}:{posid}
    # This typically matches 8-16 keys: with_tx (True/False) × exclude_pos (True/False) × posid (None + specific IDs)
    cache_keys = cache.keys(f'wallet:last_address_index:{wallet_hash}:*')
    if cache_keys:
        cache.delete(*cache_keys)


def clear_wallet_history_cache_for_txid(wallet_hash, txid):
    """
    Clear wallet history cache for specific pages that contain a given transaction.
    This is more efficient than clearing all pages, as it only clears the pages
    where the transaction actually appears.
    
    Args:
        wallet_hash: The wallet hash
        txid: The transaction ID to find and clear cache for
    """
    if not wallet_hash or not txid:
        return
    
    try:
        wallet = Wallet.objects.get(wallet_hash=wallet_hash)
    except Wallet.DoesNotExist:
        return
    
    cache = settings.REDISKV
    
    # Find all WalletHistory records for this txid and wallet
    # A transaction can appear in multiple records (different tokens/assets)
    history_records = WalletHistory.objects.filter(
        wallet=wallet,
        txid=txid
    ).exclude(amount=0).select_related('token', 'cashtoken_ft', 'cashtoken_nft')
    
    if not history_records.exists():
        return
    
    # Common page sizes used in the API
    common_page_sizes = [10, 20, 50, 100]
    
    # For each unique asset/token, find which pages contain this transaction
    for record in history_records:
        # Determine the token_key (same logic as in view_history.py)
        token_key = 'bch'  # default
        if record.cashtoken_ft:
            token_key = record.cashtoken_ft.category
        elif record.cashtoken_nft:
            token_key = record.cashtoken_nft.category
        elif record.token:
            if record.token.name == 'bch':
                token_key = 'bch'
            else:
                token_key = record.token.tokenid or str(record.token.id)
        
        # Build the base queryset matching the view's logic
        # This matches the filtering in WalletHistoryView.get() for record_type='all'
        base_qs = WalletHistory.objects.exclude(amount=0).filter(wallet=wallet)
        
        # Order by same fields as the view (tx_timestamp desc, date_created desc)
        base_qs = base_qs.order_by(
            F('tx_timestamp').desc(nulls_last=True),
            F('date_created').desc(nulls_last=True)
        )
        
        # Filter by token_key
        if token_key == 'bch':
            base_qs = base_qs.filter(
                cashtoken_ft__isnull=True,
                cashtoken_nft__isnull=True,
                token__name='bch'
            )
        else:
            # For tokens, filter by the specific token
            # Try to match by category first (for cashtokens), then by tokenid/id
            base_qs = base_qs.filter(
                Q(cashtoken_ft__category=token_key) |
                Q(cashtoken_nft__category=token_key) |
                Q(token__tokenid=token_key) |
                Q(token__id=token_key)
            )
        
        # Get the position of this transaction in the ordered list
        # We need to count how many records come before it
        record_timestamp = record.tx_timestamp
        record_date_created = record.date_created
        
        # Count records that come before this one in the ordering
        # Ordering is: tx_timestamp DESC (nulls_last=True), date_created DESC (nulls_last=True)
        # So records with:
        # - Later timestamp come first
        # - Same timestamp but later date_created come first  
        # - NULL timestamps come last
        if record_timestamp is None:
            # If this record has NULL timestamp, it's at the end
            # Count all records with non-NULL timestamps
            position = base_qs.exclude(tx_timestamp__isnull=True).count()
        else:
            # Count records that come before this one:
            # 1. Records with later timestamp (non-null)
            # 2. Records with same timestamp but later date_created (non-null)
            # 3. Records with same timestamp and date_created but lower ID (for tiebreaking)
            position_qs = base_qs.filter(tx_timestamp__isnull=False)
            
            # Records with later timestamp
            later_timestamp_count = position_qs.filter(tx_timestamp__gt=record_timestamp).count()
            
            # Records with same timestamp but later date_created
            same_timestamp_qs = position_qs.filter(tx_timestamp=record_timestamp)
            if record_date_created is None:
                # If our record has NULL date_created, count all with non-NULL date_created
                later_date_count = same_timestamp_qs.exclude(date_created__isnull=True).count()
            else:
                # Count records with same timestamp but later date_created, or same date but lower ID
                later_date_count = same_timestamp_qs.filter(
                    Q(date_created__isnull=False) & (
                        Q(date_created__gt=record_date_created) |
                        (Q(date_created=record_date_created) & Q(id__lt=record.id))
                    )
                ).count()
            
            position = later_timestamp_count + later_date_count
        
        # Calculate which pages this transaction appears on for each page size
        # The transaction appears on page = floor(position / page_size) + 1
        # Clear the page it's on, plus one page before and after to be safe
        pages_to_clear = set()
        for page_size in common_page_sizes:
            page_num = math.floor(position / page_size) + 1
            # Clear the page it's on, plus one page before and after to be safe
            for offset in [-1, 0, 1]:
                page = page_num + offset
                if page > 0:  # Page numbers start at 1
                    pages_to_clear.add((page, page_size))
        
        # Clear the specific cache keys for this token_key
        for page, page_size in pages_to_clear:
            cache_key = f'wallet:history:{wallet_hash}:{token_key}:{page}:{page_size}'
            cache.delete(cache_key)
        
        # Also clear the "all" combined history cache if it exists
        # (for when all=true parameter is used)
        for page, page_size in pages_to_clear:
            cache_key = f'wallet:history:{wallet_hash}:all:{page}:{page_size}'
            cache.delete(cache_key)


LAST_ACTIVE_TTL = 60 * 60 * 24  # 24 hours


def set_last_active(pubkey_hex, timestamp):
    """Cache the last active timestamp for a pubkey hex with a 24-hour TTL.

    Updates the cached value in place; does nothing if pubkey_hex is empty.
    Accepts a datetime (converted to ISO format) or a pre-formatted string.
    """
    if not pubkey_hex:
        return
    cache = settings.REDISKV
    cache_key = f'last_active:{pubkey_hex}'
    if isinstance(timestamp, datetime.datetime):
        timestamp = timestamp.isoformat().replace('+00:00', 'Z')
    cache.set(cache_key, str(timestamp), ex=LAST_ACTIVE_TTL)


def get_last_active(pubkey_hex):
    """Return the cached last-active ISO timestamp for a pubkey, or None."""
    if not pubkey_hex:
        return None
    cache = settings.REDISKV
    cache_key = f'last_active:{pubkey_hex}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached.decode('utf-8') if isinstance(cached, bytes) else str(cached)
    return None


def clear_last_active(pubkey_hex):
    """Remove the last-active cache entry for a pubkey hex."""
    if not pubkey_hex:
        return
    cache = settings.REDISKV
    cache_key = f'last_active:{pubkey_hex}'
    cache.delete(cache_key)


TYPING_THROTTLE_TTL = 3  # seconds


def set_typing_throttle(pubkey_hex, room_id):
    """Set a short-lived throttle key so repeated typing bursts are coalesced.

    Returns True if the key was newly set (i.e. this call was not throttled),
    False if a throttle key already existed (caller should skip the broadcast).
    """
    if not pubkey_hex or not room_id:
        return True
    cache = settings.REDISKV
    cache_key = f'typing:{pubkey_hex}:{room_id}'
    was_set = cache.set(cache_key, b'1', ex=TYPING_THROTTLE_TTL, nx=True)
    return bool(was_set)
