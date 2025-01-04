from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from rest_framework.authtoken.models import Token
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from main.utils.redis_block_setter import *
from main.models import (
    BlockHeight,
    Transaction,
    WalletPreferences,
    TransactionMetaAttribute,
    WalletHistory,
    WalletHistoryQuerySet,
    Address,
)
from main.tasks import (
    transaction_post_save_task,
    update_wallet_history_currency,
)


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

            address = Address.objects.filter(
                address_path=address_path,
                wallet__wallet_hash=instance.wallet_hash
            )
            index_address = Address.objects.filter(
                address_path=f'0/{raw_posid}',
                wallet__wallet_hash=instance.wallet_hash
            )

            if address.exists() and index_address.exists():
                address = address.first()
                index_address = index_address.first()
                
                transaction = Transaction.objects.filter(txid=instance.txid, address=index_address)
                transaction = transaction.first()
                room_name = address.address.replace(':','_') + '_'
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
        # Delete earlier wallet history records for the same txid, wallet, & record type
        WalletHistory.objects.filter(
            txid=instance.txid,
            wallet=instance.wallet,
            record_type=instance.record_type,
        ).exclude(id=instance.id).delete()
