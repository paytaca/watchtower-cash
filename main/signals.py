import logging
from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from rest_framework.authtoken.models import Token
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from main.utils.redis_block_setter import *
from main.utils.logging import log_signal_activity
from main.models import (
    BlockHeight,
    Transaction,
    WalletPreferences,
    TransactionMetaAttribute,
    WalletHistory,
    WalletHistoryQuerySet,
    Address,
    TransactionBroadcast,
)
from main.tasks import (
    transaction_post_save_task,
    update_wallet_history_currency,
)
from main.utils.cache import clear_wallet_history_cache, clear_wallet_balance_cache


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_auth_token(sender, instance=None, created=False, **kwargs):
    if created:
        Token.objects.create(user=instance)


@receiver(post_save, sender=BlockHeight)
def blockheight_post_save(sender, instance=None, created=False, **kwargs):
    if not created:
        if instance.transactions_count:
            if instance.currentcount == instance.transactions_count:
                BlockHeight.objects.filter(id=instance.id).update(processed=True, updated_datetime=timezone.now())

    if created:
        
        # Make sure there are no missed blocks
        # last_processed_block = BlockHeight.objects.filter(processed=True).last().number
        # latest_block = BlockHeight.objects.last().number
        
        # for i in range(last_processed_block, latest_block):
        #     obj, created = BlockHeight.objects.get_or_create(number=i)

        # Queue to "PENDING-BLOCKS"
        if instance.requires_full_scan:                
            block_setter(instance.number)
        

@receiver(post_save, sender=Transaction, dispatch_uid='main.tasks.transaction_post_save_task')
@log_signal_activity()
def transaction_post_save(sender, instance=None, created=False, **kwargs):
    address = instance.address.address
    blockheight_id = None
    if instance.blockheight:
        blockheight_id = instance.blockheight.id

    if instance.address.wallet:
        wallet_hash = instance.address.wallet.wallet_hash

        # delete cached bch balance
        cache = settings.REDISKV
        bch_cache_key = f'wallet:balance:bch:{wallet_hash}'
        cache.delete(bch_cache_key)

        # delete cached token balance
        category = None
        if instance.cashtoken_ft:
            category = instance.cashtoken_ft.category
        elif instance.spent and instance.spending_txid:
            # This is a spent input, try to get the category from the output
            spent_tx = Transaction.objects.filter(txid=instance.txid, index=instance.index).first()
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

    # Trigger the transaction post-save task
    transaction.on_commit(
        lambda: transaction_post_save_task.delay(address, instance.id, blockheight_id)
    )


@receiver(pre_delete, sender=Transaction, dispatch_uid='main.signals.transaction_pre_delete')
@log_signal_activity()
def transaction_pre_delete(sender, instance=None, **kwargs):
    """
    Clear cache for all wallets involved when a transaction is deleted.
    This ensures balance and history caches are invalidated for both senders and recipients.
    """
    if not instance:
        return
    
    txid = instance.txid
    
    # Find all transactions with the same txid to get all wallets involved
    # This includes the one being deleted and any others with the same txid
    all_transactions = Transaction.objects.filter(txid=txid).select_related(
        'address__wallet', 'cashtoken_ft', 'cashtoken_nft'
    )
    
    # Collect unique wallet hashes and token categories
    unique_wallet_hashes = set()
    token_categories = set()
    
    for txn in all_transactions:
        # Collect wallet hashes from addresses
        if txn.address and txn.address.wallet:
            unique_wallet_hashes.add(txn.address.wallet.wallet_hash)
        
        # Collect token categories
        if txn.cashtoken_ft:
            token_categories.add(txn.cashtoken_ft.category)
        if txn.cashtoken_nft:
            token_categories.add(txn.cashtoken_nft.category)
    
    # Also check for wallets from transactions that spent this transaction's outputs
    # These are transactions where spending_txid = txid (they spent outputs from this transaction)
    # This covers both:
    # 1. Transactions that used this transaction's outputs as inputs
    # 2. The inputs to this transaction (if this transaction spent them)
    spending_transactions = Transaction.objects.filter(spending_txid=txid).select_related('address__wallet')
    for txn in spending_transactions:
        if txn.address and txn.address.wallet:
            unique_wallet_hashes.add(txn.address.wallet.wallet_hash)
    
    # Clear balance and history cache for all wallets involved
    for wallet_hash in unique_wallet_hashes:
        # Clear BCH balance for all wallets, and token balance only for tokens involved
        if token_categories:
            clear_wallet_balance_cache(wallet_hash, token_categories)
        else:
            # Only clear BCH balance if no tokens are involved
            clear_wallet_balance_cache(wallet_hash, [])
        # Clear all history cache for the wallet
        clear_wallet_history_cache(wallet_hash)


@receiver(post_save, sender=WalletPreferences, dispatch_uid='main.tasks.update_wallet_history_currency')
def walletpreferences_post_save(sender, instance=None, created=False, **kwargs):
    if instance and instance.selected_currency and instance.wallet:
        update_wallet_history_currency.delay(instance.wallet.wallet_hash, instance.selected_currency)


@receiver(post_save, sender=TransactionMetaAttribute)
def transaction_meta_attr_post_save(sender, instance=None, created=False, **kwargs):
    # send websocket data to first POS device address
    if created:
        if 'vault_payment_' in instance.key:
            raw_posid = instance.key.split('_')[2]
            pad = "0" * (WalletHistoryQuerySet.POS_ID_MAX_DIGITS - len(raw_posid))
            posid_str = pad + raw_posid
            first_pos_index = "1" + posid_str
            address_path = "0/" + first_pos_index

            first_pos_addr = Address.objects.filter(address_path=address_path, wallet__wallet_hash=instance.wallet_hash)
            zeroth_address = Address.objects.filter(address_path='0/0', wallet__wallet_hash=instance.wallet_hash)

            if first_pos_addr.exists() and zeroth_address.exists():
                first_pos_addr = first_pos_addr.first()
                zeroth_address = zeroth_address.first()
                
                transaction = Transaction.objects.filter(txid=instance.txid, address=zeroth_address)
                transaction = transaction.first()
                room_name = first_pos_addr.address.replace(':','_') + '_'
                senders = [*Transaction.objects.filter(spending_txid=transaction.txid).values_list('address__address', flat=True)]

                data = {
                    'token_name': transaction.token.name,
                    'token_id':  transaction.token.info_id,
                    'token_symbol': transaction.token.token_ticker.lower(),
                    'amount': transaction.amount,
                    'value': transaction.value,
                    'address': transaction.address.address,
                    'source': 'WatchTower',
                    'txid': transaction.txid,
                    'index': transaction.index,
                    'address_path' : transaction.address.address_path,
                    'senders': senders,
                }
                
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    f"{room_name}", 
                    {
                        "type": "send_update",
                        "data": data
                    }
                )


@receiver(post_save, sender=WalletHistory, dispatch_uid='main.tasks.wallet_history_post_save')
def wallet_history_post_save(sender, instance=None, created=False, **kwargs):
    if created:
        # Clear wallet history cache for this wallet to ensure fresh data
        # Note: Deletion of earlier records is now handled in parse_wallet_history using update_or_create
        if instance.wallet:
            # Determine asset key for cache clearing
            asset_key = None
            if instance.cashtoken_ft:
                asset_key = instance.cashtoken_ft.category
            elif instance.cashtoken_nft:
                asset_key = instance.cashtoken_nft.category
            elif instance.token:
                # For BCH or SLP tokens, use token info_id or 'bch'
                if instance.token.name == 'bch':
                    asset_key = 'bch'
                else:
                    asset_key = instance.token.info_id if instance.token.info_id else None
            
            # Clear cache for the specific asset, or all if asset_key is None
            clear_wallet_history_cache(instance.wallet.wallet_hash, asset_key)
