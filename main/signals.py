from main.utils.bchd.bchrpc_pb2 import Transaction
from django.conf import settings
from django.db.models.signals import post_save
from main.tasks import save_record, slpdbquery_transaction, bitdbquery_transaction
from django.dispatch import receiver
from rest_framework.authtoken.models import Token
from main.models import BlockHeight, BchAddress, SlpAddress
from main.utils.queries.bchd import BCHDQuery
from main.utils.bitdb import BitDB
from main.utils.slpdb import SLPDB
from django.utils import timezone

from main.utils import block_setter
from main.utils import check_wallet_address_subscription
import base64


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_auth_token(sender, instance=None, created=False, **kwargs):
    if created:
        Token.objects.create(user=instance)


@receiver(post_save, sender=BchAddress)
def bchaddress_post_save(sender, instance=None, created=False, **kwargs):
    if created:
        address = instance.address.split('bitcoincash:')[-1]
        try:
            obj = BCHDQuery()
            outputs = obj.get_utxos(address)
            source = 'bchd-query'
            for output in outputs:
                hash = output.outpoint.hash 
                index = output.outpoint.index
                block = output.block_height
                tx_hash = bytearray(hash[::-1]).hex()
                bchaddress = 'bitcoincash:' + address
                amount = output.value / (10 ** 8)
                block, created = BlockHeight.objects.get_or_create(number=block)
                args = (
                    'bch',
                    bchaddress,
                    tx_hash,
                    amount,
                    source,
                    block.id,
                    index
                )
                trid, created = save_record(*args)            
                if created:
                    Transaction.objects.filter(id=trid).update(processed=True)
        except Exception as exc:
            obj = BitDB()
            data = obj.get_utxos(address)
            for tr_id in data:
                data_tr = obj.get_transaction(tr_id)
                bitdbquery_transaction.delay(data_tr[0], 0, 0)


@receiver(post_save, sender=SlpAddress)
def slpaddress_post_save(sender, instance=None, created=False, **kwargs):
    if created:
        address = instance.address
        try:
            obj = BCHDQuery()
            outputs = obj.get_utxos(address)
            source = 'bchd-query'
            for output in outputs:
                if output.slp_token.token_id:
                    hash = output.outpoint.hash 
                    tx_hash = bytearray(hash[::-1]).hex()
                    index = output.outpoint.index
                    token_id = bytearray(output.slp_token.token_id).hex() 
                    amount = output.slp_token.amount / (10 ** output.slp_token.decimals)
                    slp_address = 'simpleledger:' + output.slp_token.address
                    block = output.block_height
                    block, created = BlockHeight.objects.get_or_create(number=block)
                    args = (
                        token_id,
                        slp_address,
                        tx_hash,
                        amount,
                        source,
                        block.id,
                        index
                    )
                    trid, created = save_record(*args)
                    if created:
                        Transaction.objects.filter(id=trid).update(processed=True)
            
        except Exception:
            obj = SLPDB()
            data = obj.get_utxos(address)
            for tr_id in data:
                data_tr = obj.get_transaction(tr_id)
                slpdbquery_transaction.delay(data_tr[0], 0, 0)


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
                                
        block_setter(instance.number)
        
