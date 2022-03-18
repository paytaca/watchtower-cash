import logging
from celery import shared_task
from django.conf import settings

from smartbch.conf import settings as app_settings
from smartbch.models import Block
from smartbch.utils import block as block_utils
from smartbch.utils import transaction as transaction_utils

LOGGER = logging.getLogger(__name__)
REDIS_CLIENT = settings.REDISKV

## Redis names used
_REDIS_NAME__BLOCKS_BEING_PARSED = 'smartbch:blocks-being-parsed'
_REDIS_NAME__TXS_TRANSFERS_BEING_PARSED = 'smartbch:tx-transfers-being-parsed'

@shared_task
def preload_new_blocks_task():
    LOGGER.info("Preloading new blocks to db")

    (start_block, end_block) = block_utils.preload_new_blocks()
    LOGGER.info(f"Preloaded blocks from {start_block} to {end_block}")
    return (start_block, end_block)

@shared_task
def parse_blocks_task():
    LOGGER.info("Parsing new blocks")

    block_count = None
    if isinstance(app_settings.BLOCKS_PER_TASK, int):
        LOGGER.info(f"Using app settings for number of blocks to parse: {app_settings.BLOCKS_PER_TASK}")
        block_count = app_settings.BLOCKS_PER_TASK
    else:
        LOGGER.info(f"Using fallback settings for number of blocks to parse: 5")
        block_count = 5

    blocks_being_parsed = REDIS_CLIENT.smembers(_REDIS_NAME__BLOCKS_BEING_PARSED)
    blocks_being_parsed = [i.decode() for i in blocks_being_parsed]

    blocks = Block.objects.exclude(
        block_number__in=blocks_being_parsed
    ).exclude(
        processed=True
    ).order_by(
        'block_number'
    )[:block_count]

    LOGGER.info(f"Queueing blocks for parsing: {blocks.values_list('block_number', flat=True)}")
    for block_obj in blocks:
        parse_block_task.delay(block_obj.block_number)
    

@shared_task
def parse_block_task(block_number):
    LOGGER.info(f"Parsing block: {block_number}")
    LOGGER.info(f"Active blocks: {REDIS_CLIENT.smembers(_REDIS_NAME__BLOCKS_BEING_PARSED)}")

    try:
        block_number = int(block_number)
    except (TypeError, ValueError):
        LOGGER.info(f"Block number ({block_number}) is invalid")
        return f"invalid_block: {block_number}"

    if REDIS_CLIENT.exists(_REDIS_NAME__BLOCKS_BEING_PARSED, str(block_number)):
        LOGGER.info(f"Block number ({block_number}) is being parsed by another task, will stop task")
        return f"block_is_being_parsed {block_number}"

    REDIS_CLIENT.sadd(_REDIS_NAME__BLOCKS_BEING_PARSED, str(block_number))
    try:
        block_obj = block_utils.parse_block(block_number, save_transactions=True)
        LOGGER.info(f"Parsed block successfully: {block_obj}")

        LOGGER.info(f"Parsing transaction transfers under block: {block_obj}")
        for tx_obj in block_obj.transactions.all():
            save_transaction_transfers_task.delay(tx_obj.txid)

    except Exception as e:
        return f"parse_block_task({block_number}) error: {str(e)}"
    finally:
        REDIS_CLIENT.srem(_REDIS_NAME__BLOCKS_BEING_PARSED, str(block_number))


@shared_task
def save_transaction_transfers_task(txid):
    LOGGER.info(f"Parsing transaction transfers: {txid}")
    LOGGER.info(f"Active transaction: {REDIS_CLIENT.smembers(_REDIS_NAME__TXS_TRANSFERS_BEING_PARSED)}")

    if REDIS_CLIENT.exists(_REDIS_NAME__TXS_TRANSFERS_BEING_PARSED, str(txid)):
        LOGGER.info(f"Transaction ({txid}) is being parsed by another task, will stop task")
        return f"transaction_is_being_parsed: {txid}"

    REDIS_CLIENT.sadd(_REDIS_NAME__TXS_TRANSFERS_BEING_PARSED, str(txid))

    try:
        tx_obj = transaction_utils.save_transaction_transfers(str(txid))
        if tx_obj:
            LOGGER.info(f"Parsed transaction transfers successfully: {tx_obj}")
            return f"parsed transaction transfers: {txid}"
        else:
            LOGGER.info(f"Unable to parse transaction transfer, transaction is not saved: {tx_obj}")
            return f"Unable to parse transaction transfer, transaction is not saved: {tx_obj}"

    except Exception as e:
        return f"save_transaction_transfers_task({txid}) error: {str(e)}"
    finally:
        REDIS_CLIENT.srem(_REDIS_NAME__TXS_TRANSFERS_BEING_PARSED, str(txid))
