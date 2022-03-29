import decimal
import datetime
from django.db import models
from django.utils.timezone import make_aware
from web3.datastructures import AttributeDict
from web3.exceptions import (
    InvalidEventABI,
    LogTopicError,
    MismatchedABI,
)

from main.models import Address

from smartbch.conf import settings as app_settings
from smartbch.models import Block, Transaction

from .contract import abi
from .formatters import format_block_number
from .web3 import create_web3_client


def range_with_exclude(*args, to_exclude=[], **kwargs):
    # This should work with new 
    for i in range(*args, **kwargs):
        if i in to_exclude:
            continue
        yield i

def preload_block_range(start_block, end_block):
    """
        Preloads block range to database creates blocks within the specified range that are not yet in database

    Parameters
    ------------
    start_block: int | decimal.Decimal
    end_block: int | decimal.Decimal

    Returns
    ------------
    (start_block, end_block, blocks_created)
        blocks_created: list(smartbch.models.Block)
            new blocks created, i.e. blocks within the specified range that have already existed are not included here
    """
    print(f"Pre saving blocks from {start_block} to {end_block}")
    existing_block_numbers = Block.objects.filter(
        block_number__gte=start_block, block_number__lte=end_block
    ).order_by(
        "block_number",
    ).values_list(
        "block_number", flat=True,
    )

    created_blocks = []
    # blocks_to_create = []
    for block_number in range(int(start_block), int(end_block)+1):
        block, created = Block.objects.get_or_create(
            block_number=decimal.Decimal(block_number),
        )
        if created:
            created_blocks.append(block)
    
    # if len(blocks_to_create):
    #     created_blocks = Block.objects.bulk_create(blocks_to_create)

    return (start_block, end_block, created_blocks)


def preload_new_blocks(blocks_to_preload=app_settings.BLOCK_TO_PRELOAD):
    """
        Preloads a specified number of blocks relative to the chain's latest block number to the database.

    Parameters
    ------------
    blocks_to_preload: number, decimal.Decimal
        Used to determine the start block, the specified value is subtracted to the latest block number

    Returns
    ------------
        see `preload_block_range(start_block, end_block)`
    """
    w3 = create_web3_client()
    latest_block = w3.eth.block_number

    # a hard coded value in case the parameter is not specified 
    if not isinstance(blocks_to_preload, (int, decimal.Decimal)) or blocks_to_preload <= 0:
        blocks_to_preload = 500

    # a guard to set the start block, it implies the start block must be positive and
    # greater than or equal to app_setting.START_BLOCK
    HARD_START_BLOCK = 0
    if isinstance(app_settings.START_BLOCK, (int, decimal.Decimal)):
        HARD_START_BLOCK = max(0, app_settings.START_BLOCK)

    start_block = max(HARD_START_BLOCK, latest_block - blocks_to_preload)

    return preload_block_range(start_block, latest_block)

def parse_block(block_number, save_transactions=True, save_all_transactions=False):
    """
        Parse block and save to db
    
    Parameters
    ------------
    save_transactions: boolean
        Flag to determine whether to save the transactions inside the block to the database

    save_all_transactions: boolean
        Only meaningful when `save_transactions=True`, will save all the transactions under the block i.e.
        it will save transactions even if no address is subscribed.

    Returns
    ------------
        block: smartbch.models.Block
    """
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

    # ERC20 and ERC721 Transfer event topic, apparenlty share the same topic in hex string
    event_topic = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
    block_logs = w3.eth.get_logs({
        "fromBlock": format_block_number(block_number),
        "toBlock": format_block_number(block_number),
        "topics": [event_topic],
    })

    if save_transactions:
        tx_log_addresses_map = {}
        if not save_all_transactions:
            erc20 = w3.eth.contract('', abi=abi.get_token_abi(20))
            erc721 = w3.eth.contract('', abi=abi.get_token_abi(721))
            # extracting the addresses of the Transfer events in logs
            for log in block_logs:
                tx_hex = ""
                addresses = set()
                try:
                    parsed_log = erc20.events.Transfer().processLog(log)
                    tx_hex = parsed_log.transactionHash.hex()
                    addresses.add(parsed_log.args['from'])
                    addresses.add(parsed_log.args.to)
                except (InvalidEventABI, LogTopicError, MismatchedABI):
                    pass

                try:
                    parsed_log = erc721.events.Transfer().processLog(log)
                    tx_hex = parsed_log.transactionHash.hex()
                    addresses.add(parsed_log.args['from'])
                    addresses.add(parsed_log.args.to)
                except (InvalidEventABI, LogTopicError, MismatchedABI):
                    pass

                if tx_hex:
                    tx_log_addresses_map[tx_hex] = addresses

        for transaction in block.transactions:
            if not save_all_transactions:
                tx_addresses_list = [
                    transaction['from'],
                    transaction.to,
                ]
                if isinstance(tx_log_addresses_map.get(transaction.hash.hex(), None), (set, list)):
                    tx_addresses_list = [
                        *tx_addresses_list,
                        *tx_log_addresses_map[transaction.hash.hex()],
                    ]

                tracked_addresses = Address.objects.filter(address__in=tx_addresses_list)
                if not tracked_addresses.exists():
                    continue

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
