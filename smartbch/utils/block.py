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

    # ERC20 and ERC721 Transfer event topic, apparenlty share the same topic in hex string
    event_topic = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
    block_logs = w3.eth.get_logs({
        "fromBlock": format_block_number(block_number),
        "toBlock": format_block_number(block_number),
        "topics": [event_topic],
    })

    erc20 = w3.eth.contract('', abi=abi.get_token_abi(20))
    erc721 = w3.eth.contract('', abi=abi.get_token_abi(721))
    tx_log_addresses_map = {}
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

    if save_transactions:
        for transaction in block.transactions:
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
