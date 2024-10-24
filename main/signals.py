from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from rest_framework.authtoken.models import Token
from django.utils import timezone
from main.utils.redis_block_setter import *
from main.models import (
    BlockHeight,
    Transaction,
    WalletPreferences,
    TransactionMetaAttribute,
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
            posid_str = instance.key.split('_')[2]
            pad = "0" * (WalletHistoryQuerySet.POS_ID_MAX_DIGITS - len(posid_str))
            posid_str = pad + posid_str
            first_pos_index = "1" + posid_str
            address_path = "0/" + first_pos_index

            address = Address.objects.filter(
                address_path=address_path,
                wallet__wallet_hash=instance.wallet_hash
            )

            if address.exists():
                address = address.first()
                transaction = Transaction.objects.get(txid=instance.txid)
                room_name = transaction.address.address.replace(':','_') + '_'
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