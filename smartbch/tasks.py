import logging
import web3
import requests
import decimal
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.db import models
from django.utils import timezone

from smartbch.conf import settings as app_settings
from smartbch.models import (
    Block,
    Transaction,
    TransactionTransfer,
    TokenContract,
)
from smartbch.utils import block as block_utils
from smartbch.utils import subscription as subscription_utils
from smartbch.utils import transaction as transaction_utils
from smartbch.utils import contract as contract_utils
from smartbch.utils import push_notification as push_notification_utils
from main.tasks import download_image

LOGGER = logging.getLogger(__name__)
REDIS_CLIENT = settings.REDISKV

## Redis names used
_REDIS_KEY_TTL = 300 # 5 minutes
_REDIS_NAME__BLOCKS_BEING_PARSED = 'smartbch:blocks-being-parsed'
_REDIS_NAME__TXS_BEING_PARSED = 'smartbch:txs-being-parsed'
_REDIS_NAME__TXS_TRANSFERS_BEING_PARSED = 'smartbch:tx-transfers-being-parsed'
_REDIS_NAME__ADDRESS_BEING_CRAWLED = 'smartbch:address-being-crawled'

## CELERY QUEUES
_TASK_TIME_LIMIT = 300 # 5 minutes
_QUEUE_BLOCKS_PARSER = "sbch__blocks_parser_queue"
_QUEUE_TRANSACTIONS_PARSER = "sbch__transactions_parser_queue"
_QUEUE_ADDRESS_PARSER = "sbch__address_parser_queue"
_QUEUE_TRANSACTION_TRANSFER_NOTIFICATION = "sbch__transaction_transfer_notification_queue"

@shared_task(queue=_QUEUE_BLOCKS_PARSER, time_limit=_TASK_TIME_LIMIT)
def preload_new_blocks_task():
    LOGGER.info("Preloading new blocks to db")

    (start_block, end_block, _) = block_utils.preload_new_blocks()
    LOGGER.info(f"Preloaded blocks from {start_block} to {end_block}")
    return (start_block, end_block)

@shared_task(queue=_QUEUE_BLOCKS_PARSER, time_limit=_TASK_TIME_LIMIT)
def parse_missed_records_task():
    parse_missing_blocks_task.delay()
    handle_transactions_with_unprocessed_transfers_task.delay()

@shared_task(queue=_QUEUE_BLOCKS_PARSER, time_limit=_TASK_TIME_LIMIT)
def parse_missing_blocks_task():
    """
        Parse missing block numbers in the database
    """
    LOGGER.info("Parsing for missing blocks")
    # a hard limit to cap load
    MAX_BLOCKS_TO_PARSE = 25

    block_numbers = Block.get_missing_block_numbers(
        limit=MAX_BLOCKS_TO_PARSE,
        lookback_size=1000,
    )

    LOGGER.info(f"Found {len(block_numbers)} missing block_numbers")
    for block_number in block_numbers:
        parse_block_task.delay(block_number)

    return f"Sent blocks: {block_numbers}"


@shared_task(queue=_QUEUE_TRANSACTIONS_PARSER, time_limit=_TASK_TIME_LIMIT)
def handle_transactions_with_unprocessed_transfers_task():
    """
        Look for transactions with unprocessed transaction transfers and queue for parsing transfers
        Starting from txs with earliest block number to prevent unsent transactions
    """
    LOGGER.info("Looking for transactions with unprocessed transfers transaction transfers")
    MAX_TXS_TO_PROCESS = 50
    unsaved_transactions = Transaction.objects.filter(
        processed_transfers=False,
    ).order_by(
        "block__block_number",
    )

    transactions_to_process = unsaved_transactions[:MAX_TXS_TO_PROCESS]
    blocks_without_timestamp = Block.objects.filter(
        transactions__in=transactions_to_process,
        timestamp__isnull=True,
        processed=False,
    ).values_list("block_number", flat=True)

    LOGGER.info(f"Detected blocks without timestamp, will resolve them: {blocks_without_timestamp}")
    for block_number in blocks_without_timestamp:
        block_utils.parse_block(block_number, save_transactions=False)

    LOGGER.info(f"Found {unsaved_transactions.count()} transactions with unprocessed transfers, queueing {MAX_TXS_TO_PROCESS} txs for processing")
    now = timezone.now()
    for tx_obj in transactions_to_process:
        send_notifications = False
        if tx_obj.block.timestamp is not None:
            tx_age = now - tx_obj.block.timestamp

            # if transaction age is 1 hour, send the notification
            if tx_age.total_seconds() > 3600:
                send_notifications = True

        save_transaction_transfers_task.delay(tx_obj.txid, send_notifications=send_notifications)


@shared_task(queue=_QUEUE_BLOCKS_PARSER, time_limit=_TASK_TIME_LIMIT)
def parse_blocks_task():
    LOGGER.info("Parsing new blocks")

    block_count = None
    if isinstance(app_settings.BLOCKS_PER_TASK, int):
        LOGGER.info(f"Using app settings for number of blocks to parse: {app_settings.BLOCKS_PER_TASK}")
        block_count = app_settings.BLOCKS_PER_TASK
    else:
        LOGGER.info(f"Using fallback settings for number of blocks to parse: 25")
        block_count = 25

    blocks_being_parsed = REDIS_CLIENT.smembers(_REDIS_NAME__BLOCKS_BEING_PARSED)
    blocks_being_parsed = [i.decode() for i in blocks_being_parsed]

    blocks = Block.objects.exclude(
        block_number__in=blocks_being_parsed
    ).exclude(
        processed=True
    ).order_by(
        '-block_number'
    )[:block_count]

    LOGGER.info(f"Queueing blocks for parsing: {blocks.values_list('block_number', flat=True)}")
    for block_obj in blocks:
        parse_block_task.delay(block_obj.block_number, send_notifications=True)
    

@shared_task(queue=_QUEUE_BLOCKS_PARSER, time_limit=_TASK_TIME_LIMIT)
def parse_block_task(block_number, send_notifications=False):
    active_blocks = REDIS_CLIENT.smembers(_REDIS_NAME__BLOCKS_BEING_PARSED)
    LOGGER.info(f"Parsing block: {block_number}")
    LOGGER.info(f"Active blocks: {active_blocks}")

    try:
        block_number = int(block_number)
    except (TypeError, ValueError):
        LOGGER.info(f"Block number ({block_number}) is invalid")
        return f"invalid_block: {block_number}"

    if str(block_number) in active_blocks:
        LOGGER.info(f"Block number ({block_number}) is being parsed by another task, will stop task")
        return f"block_is_being_parsed {block_number}: {active_blocks}"

    REDIS_CLIENT.sadd(_REDIS_NAME__BLOCKS_BEING_PARSED, str(block_number))
    REDIS_CLIENT.expire(_REDIS_NAME__BLOCKS_BEING_PARSED, _REDIS_KEY_TTL)
    try:
        block_obj = block_utils.parse_block(block_number, save_transactions=True)
        LOGGER.info(f"Parsed block successfully: {block_obj}")

        LOGGER.info(f"Parsing transaction transfers under block: {block_obj}")
        for tx_obj in block_obj.transactions.all():
            save_transaction_transfers_task.delay(tx_obj.txid, send_notifications=send_notifications)

    except Exception as e:
        return f"parse_block_task({block_number}) error: {str(e)}"
    finally:
        REDIS_CLIENT.srem(_REDIS_NAME__BLOCKS_BEING_PARSED, str(block_number))


@shared_task(queue=_QUEUE_TRANSACTIONS_PARSER, time_limit=_TASK_TIME_LIMIT)
def save_transaction_transfers_task(txid, send_notifications=False):
    LOGGER.info(f"Parsing transaction transfers: {txid}")
    LOGGER.info(f"Active transaction: {REDIS_CLIENT.smembers(_REDIS_NAME__TXS_TRANSFERS_BEING_PARSED)}")

    if REDIS_CLIENT.exists(_REDIS_NAME__TXS_TRANSFERS_BEING_PARSED, str(txid)):
        LOGGER.info(f"Transaction ({txid}) is being parsed by another task, will stop task")
        return f"transaction_is_being_parsed: {txid}"

    REDIS_CLIENT.sadd(_REDIS_NAME__TXS_TRANSFERS_BEING_PARSED, str(txid))
    REDIS_CLIENT.expire(_REDIS_NAME__TXS_TRANSFERS_BEING_PARSED, _REDIS_KEY_TTL)

    try:
        tx_obj = transaction_utils.save_transaction_transfers(str(txid), parse_block_timestamp=True)
        if tx_obj:
            LOGGER.info(f"Parsed transaction transfers successfully: {tx_obj}")
            if send_notifications:
                LOGGER.info(f"Queueing to send notfication for transaction: {tx_obj}")
                send_transaction_notification_task.delay(tx_obj.txid)

            return f"parsed transaction transfers: {txid}"
        else:
            LOGGER.info(f"Unable to parse transaction transfer, transaction is not saved: {tx_obj}")
            return f"Unable to parse transaction transfer, transaction is not saved: {tx_obj}"

    except Exception as e:
        return f"save_transaction_transfers_task({txid}) error: {str(e)}"
    finally:
        REDIS_CLIENT.srem(_REDIS_NAME__TXS_TRANSFERS_BEING_PARSED, str(txid))


@shared_task(queue=_QUEUE_TRANSACTIONS_PARSER, time_limit=_TASK_TIME_LIMIT)
def save_transaction_task(txid):
    LOGGER.info(f"Parsing transaction: {txid}")

    if REDIS_CLIENT.exists(_REDIS_NAME__TXS_BEING_PARSED, str(txid)):
        LOGGER.info(f"Transaction ({txid}) is being parsed by another task, will stop task")
        return f"transaction_is_being_parsed: {txid}"

    REDIS_CLIENT.sadd(_REDIS_NAME__TXS_BEING_PARSED, str(txid))
    REDIS_CLIENT.expire(_REDIS_NAME__TXS_BEING_PARSED, _REDIS_KEY_TTL)

    try:
        tx_obj = transaction_utils.save_transaction(str(txid))
        LOGGER.info(f"Parsed transaction successfully: {tx_obj}")
        LOGGER.info(f"Queueing task for saving transaction transfers of: {tx_obj.txid}")
        save_transaction_transfers_task.delay(tx_obj.txid)
        return f"parsed transaction: {txid}"
    except Exception as e:
        return f"save_transaction_task({txid}) error: {str(e)}"
    finally:
        REDIS_CLIENT.srem(_REDIS_NAME__TXS_BEING_PARSED, str(txid))


@shared_task(queue=_QUEUE_ADDRESS_PARSER, time_limit=_TASK_TIME_LIMIT)
def save_transactions_by_address(address):
    LOGGER.info(f"Crawling transactions of: {address}")
    if not web3.Web3.isAddress(address):
        LOGGER.info(f"Address ({address}) is invalid")
        return f"address_invalid: {address}"

    if REDIS_CLIENT.exists(_REDIS_NAME__ADDRESS_BEING_CRAWLED, str(address)):
        LOGGER.info(f"Address ({address}) is being parsed by another task, will stop task")
        return f"address_is_being_crawled: {address}"

    REDIS_CLIENT.sadd(_REDIS_NAME__ADDRESS_BEING_CRAWLED, str(address))
    REDIS_CLIENT.expire(_REDIS_NAME__ADDRESS_BEING_CRAWLED, _REDIS_KEY_TTL)

    # we expect other tasks to save the newer unprocessed blocks
    end_block = Block.objects.filter(processed=True).aggregate(latest_block = models.Max('block_number')).get('latest_block')

    is_numeric = lambda var: isinstance(var, (int, decimal.Decimal))
    start_block = app_settings.START_BLOCK
    if not is_numeric(start_block):
        start_block = Block.objects.filter(processed=True).aggregate(earliest_parsed_block = models.Min('block_number')).get('earliest_parsed_block')

    # just added a guard to limit the block to backtrack to 125 blocks
    if not is_numeric(start_block) or end_block - start_block > 125:
        start_block = end_block - 125

    iterator = transaction_utils.get_transactions_by_address(
        address,
        from_block=start_block,
        to_block=end_block,
        block_partition=10,
    )

    for tx_list in iterator:
        for tx in tx_list.transactions:
            save_transaction_task.delay(tx.hash)

@shared_task(queue=_QUEUE_ADDRESS_PARSER, time_limit=_TASK_TIME_LIMIT)
def save_transactions_by_address_task__manual(address, from_block=0, to_block=0, block_partition=0):
    iterator = transaction_utils.get_transactions_by_address(
        address,
        from_block=int(from_block),
        to_block=int(to_block),
        block_partition=int(block_partition),
    )

    for tx_list in iterator:
        for tx in tx_list.transactions:
            save_transaction_task.delay(tx.hash)


@shared_task(queue=_QUEUE_TRANSACTION_TRANSFER_NOTIFICATION, time_limit=_TASK_TIME_LIMIT)
def send_transaction_notification_task(txid):
    tx_obj = Transaction.objects.filter(txid=txid).first()

    if not tx_obj:
        return f"transaction with id {txid} does not exist"

    for transfer_tx in tx_obj.transfers.all():
        send_transaction_transfer_notification_task.delay(transfer_tx.id)


@shared_task(queue=_QUEUE_TRANSACTION_TRANSFER_NOTIFICATION, max_retries=3, time_limit=_TASK_TIME_LIMIT)
def send_transaction_transfer_notification_task(tx_transfer_id):
    tx_transfer_obj = TransactionTransfer.objects.filter(id=tx_transfer_id).first()

    if not tx_transfer_obj:
        return f"transaction_transfer with id {tx_transfer_id} does not exist"

    try:
        push_notification_utils.send_transaction_transfer_push_notification(tx_transfer_obj)
    except Exception as exception:
        LOGGER.exception(exception)

    subscriptions = tx_transfer_obj.get_unsent_valid_subscriptions()

    if subscriptions is None or not subscriptions.exists():
        return f"transaction_transfer with id {tx_transfer_id} has no related valid subscriptions"

    if tx_transfer_obj.token_contract:
        contract_utils.get_or_save_token_contract_metadata(
            tx_transfer_obj.token_contract.address,
            force=False,
        )

    log_ids = []
    failed_subs = []
    for subscription in subscriptions:
        log, error = subscription_utils.send_transaction_transfer_notification_to_subscriber(
            subscription,
            tx_transfer_obj,
        )

        if log:
            log_ids.append(log.id)
        elif error:
            failed_subs.append(
                (subscription, error)
            )

    resp = []
    if len(log_ids):
        LOGGER.info(f"sucessfully sent subscription notifications: {log_ids}")
        resp.append(f"sent {len(log_ids)} transaction_transfer notifications, log_ids: {log_ids}")

    if len(failed_subs):
        LOGGER.info(f"Failed to send subscription notifications: {failed_subs}")
        resp.append(f"error sending {len(failed_subs)} transaction_transfer notifications: {failed_subs}")
        self.retry(countdown=3)

    return "\n".join(resp)


@shared_task(queue=_QUEUE_ADDRESS_PARSER, time_limit=_TASK_TIME_LIMIT)
def parse_token_contract_metadata_task():
    LOGGER.info(f"Checking for token contracts without metadata")
    MAX_CONTRACTS_PER_TASK = 10
    token_contract_addresses = TokenContract.objects.filter(
        name__isnull=True,
        symbol__isnull=True,
    )[:MAX_CONTRACTS_PER_TASK].values_list("address", flat=True)

    if not len(token_contract_addresses):
        LOGGER.info(f"No token contracts without metadata found")
        return "no_token_contract_found"

    LOGGER.info(f"Found {len(token_contract_addresses)} token contract/s without metadata: {token_contract_addresses}")
    results = []
    for address in token_contract_addresses:
        instance, updated = contract_utils.get_or_save_token_contract_metadata(address, force=False)
        instance_id = instance.id if instance else None
        results.append({
            "id": instance_id,
            "address": address,
            "updated": updated,
        })

    return results

@shared_task(queue=_QUEUE_ADDRESS_PARSER, time_limit=_TASK_TIME_LIMIT)
def save_token_icons_task():
    LOGGER.info(f"Checking for token contracts without icons")
    MAX_CONTRACTS_PER_TASK = 10

    token_contracts = TokenContract.objects.filter(image_url__isnull=True)[:MAX_CONTRACTS_PER_TASK]
    if not len(token_contracts):
        LOGGER.info(f"No token contracts without icon found")
        return "no_token_contract_found"

    LOGGER.info(f"Found {len(token_contracts)} token contract/s without urls: {token_contracts}")

    address_image_map = contract_utils.fetch_icons_from_marketcap() or {}
    results = []
    for token_contract in token_contracts:
        url = f"https://www.smartscout.cash/assets/images/tokens/{token_contract.address}.png"
        src = "smartscan"
        if token_contract.address.lower() in address_image_map and address_image_map[token_contract.address.lower()]:
            url = address_image_map[token_contract.address.lower()]
            src = "marketcap"
        response = requests.get(url)

        content_type = f"{response.headers.get('Content-Header', None)}".split("/")
        is_image = len(content_type) > 0 and content_type[0] == "image"

        status_code, image_file_name = download_image(token_contract.address, url, resize=True)

        image_server_base = 'https://images.watchtower.cash'
        image_url = f"{image_server_base}/{image_file_name}"
        if status_code != 200 or not image_file_name:
            image_url = ""

        token_contract.image_url = image_url
        token_contract.image_url_source = src
        token_contract.save()
        results.append(
            [token_contract.address, image_url]
        )

    return results
