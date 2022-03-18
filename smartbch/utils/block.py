import decimal
import datetime
from django.db import models
from django.utils.timezone import make_aware

from smartbch.conf import settings as app_settings
from smartbch.models import Block, Transaction

from .web3 import create_web3_client

def preload_new_blocks(force_start_block=None):
    w3 = create_web3_client()
    latest_block = w3.eth.block_number

    last_saved_block = Block.objects.aggregate(latest_block = models.Max('block_number')).get('latest_block')

    start_block = latest_block
    if last_saved_block is not None and last_saved_block > 0:
        start_block = last_saved_block
    elif app_settings.START_BLOCK is not None and app_settings.START_BLOCK > 1:
        start_block = app_settings.START_BLOCK-1

    if force_start_block is not None and force_start_block > 0 and force_start_block < latest_block:
        start_block = force_start_block

    print(f"Pre saving blocks from {start_block} to {latest_block}")
    for block_number in range(int(start_block), latest_block+1):
        Block.objects.get_or_create(
            block_number=decimal.Decimal(block_number),
        )
    return (start_block, latest_block)

def parse_block(block_number, save_transactions=True):
    w3 = create_web3_client()

    block = w3.eth.get_block(block_number, save_transactions)

    block_obj, created = Block.objects.update_or_create(
        block_number=decimal.Decimal(block_number),
        defaults={
            "timestamp": make_aware(datetime.datetime.fromtimestamp(block.timestamp)),
            "transactions_count": len(block.transactions),
            "processed": save_transactions,
        }
    )

    if save_transactions:
        for transaction in block.transactions:
            # TODO: Add condition to only save transactions that contain subscribed address
            tx, created = Transaction.objects.get_or_create(
                txid=transaction.hash.hex(),
                defaults = {
                    "block": block_obj,
                    "to_addr": transaction.to,
                    "from_addr": transaction['from'],
                    "value": w3.fromWei(transaction.value, 'ether'),
                    "data": transaction.input,
                    "gas": transaction.gas,
                    "gas_price": transaction.gasPrice,
                    "is_mined": True,
                }
            )

    return block_obj
