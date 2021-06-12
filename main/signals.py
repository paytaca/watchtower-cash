from django.conf import settings
from django.db.models.signals import post_save
from main.tasks import save_record, slpdbquery_transaction, bitdbquery_transaction
from django.dispatch import receiver
from rest_framework.authtoken.models import Token
from django.utils import timezone
from main.utils import block_setter
from main.utils.queries.bchd import BCHDQuery
from main.utils.converter import convert_bch_to_slp_address
from main.models import BlockHeight, Transaction


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
        
        # Queue to "PENDING-BLOCKS"
        beg = BlockHeight.objects.first().number
        end = BlockHeight.objects.last().number
        
        _all = list(BlockHeight.objects.values_list('number', flat=True))

        for i in range(beg, end):
            if i not in _all:
                obj, created = BlockHeight.objects.get_or_create(number=i)
        if instance.requires_full_scan:                
            block_setter(instance.number)
        

@receiver(post_save, sender=Transaction)
def transaction_post_save(sender, instance=None, created=False, **kwargs):
    if instance.address.startswith('bitcoincash:'):
        # Make sure that any SLP transaction related to this tx is saved
        slp_address = convert_bch_to_slp_address(instance.address)
        slp_txn_check = Transaction.objects.filter(
            txid=instance.txid,
            address=slp_address
        )
        if not slp_txn_check.exists():
            bchd = BCHDQuery()
            slp_tx = bchd.get_transaction(instance.txid, parse_slp=True)
            if slp_tx['valid']:
                output = None
                for tx_output in slp_tx['outputs']:
                    if tx_output['address'] == slp_address:
                        output = tx_output
                if instance.blockheight:
                    blockheight_id = instance.blockheight.id
                args = (
                    slp_tx['token_id'],
                    slp_address,
                    slp_tx['txid'],
                    output['amount'],
                    'bchd-query',
                    blockheight_id,
                    slp_tx['index']
                )
                save_record(*args)
