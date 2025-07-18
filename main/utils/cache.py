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