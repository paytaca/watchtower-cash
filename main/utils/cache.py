import base64
import pickle

from django.conf import settings

from main.models import Transaction


def clear_transaction_cache(transaction_instance):
    """
    Utility function to clear cache for a transaction.
    This can be called when transactions are updated using .update() 
    which doesn't trigger Django signals.
    """
    if not transaction_instance.address or not transaction_instance.address.wallet:
        return
    
    wallet_hash = transaction_instance.address.wallet.wallet_hash
    cache = settings.REDISKV
    
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
    """
    if not transaction_queryset.exists():
        return
    
    # Get unique wallet hashes and categories from the transactions
    wallet_hashes = set()
    categories = set()
    
    for txn in transaction_queryset.select_related('address__wallet', 'cashtoken_ft'):
        if txn.address and txn.address.wallet:
            wallet_hashes.add(txn.address.wallet.wallet_hash)
            
            if txn.cashtoken_ft:
                categories.add(txn.cashtoken_ft.category)
            elif txn.spent and txn.spending_txid:
                # This is a spent input, try to get the category from the output
                spent_tx = Transaction.objects.filter(txid=txn.txid, index=txn.index).first()
                if spent_tx and spent_tx.cashtoken_ft:
                    categories.add(spent_tx.cashtoken_ft.category)
    
    cache = settings.REDISKV
    
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