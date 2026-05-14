import base64
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