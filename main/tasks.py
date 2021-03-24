"""
Dedicated to all celery tasks for watchtower Only
"""
from __future__ import absolute_import, unicode_literals
import logging
from celery import shared_task
import requests
from main.models import (
    BlockHeight, 
    Token, 
    Transaction,
    SlpAddress, 
    Subscription, 
    BchAddress,
    SendTo,
    Subscriber
)
from django.contrib.auth.models import User
from celery.exceptions import MaxRetriesExceededError 
import json, random, time
from main.utils import check_wallet_address_subscription, check_token_subscription
from main.utils import slpdb as slpdb_scanner
from main.utils import bitdb as bitdb_scanner
from main.utils.restbitcoin import RestBitcoin
from main.utils.spicebot_token_registration import SpicebotTokens
from django.conf import settings
import traceback, datetime
from sseclient import SSEClient
from django.db import transaction as trans
import sseclient
from psycopg2.extensions import TransactionRollbackError
from django.db.utils import IntegrityError, OperationalError
from django.utils import timezone
from django.db.models import Q
from celery import Celery


LOGGER = logging.getLogger(__name__)
REDIS_STORAGE = settings.REDISKV

app = Celery('configs')

# NOTIFICATIONS
@shared_task(rate_limit='20/s', queue='send_telegram_message')
def send_telegram_message(message, chat_id, update_id=None, reply_markup=None):
    LOGGER.info(f'SENDING TO {chat_id}')
    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    if reply_markup:
        data['reply_markup'] = json.dumps(reply_markup, separators=(',', ':'))

    url = 'https://api.telegram.org/bot'
    response = requests.post(
        f"{url}{settings.TELEGRAM_BOT_TOKEN}/sendMessage", data=data
    )
    return f"send notification to {chat_id}"
    
@shared_task(rate_limit='20/s', queue='send_slack_message')
def send_slack_message(message, channel, attachments=None):
    LOGGER.info(f'SENDING TO {channel}')
    data = {
        "token": settings.SLACK_BOT_USER_TOKEN,
        "channel": channel,
        "text": message
    }

    if type(attachments) is list:
        data['attachments'] = json.dumps(attachments)

    response = requests.post(
        "https://slack.com/api/chat.postMessage",
        data=data
    )
    return f"send notification to {channel}"

@shared_task(bind=True, queue='client_acknowledgement', max_retries=3)
def client_acknowledgement(self, txid):
    with trans.atomic():
        this_transaction = Transaction.objects.filter(id=txid)

        if this_transaction.exists():
            transaction = this_transaction.first()
            block = None
            if transaction.blockheight:
                block = transaction.blockheight.number

            address = transaction.address 
            subscription = check_wallet_address_subscription(address)

            if subscription.exists():
                transaction.subscribed = True
                subscription = subscription.first()
                webhook_addresses = subscription.address.all()
                for webhook_address in webhook_addresses:
                    # can_be_send = check_token_subscription(transaction.token.tokenid, subscription.id)
                    can_be_send = True
                    if can_be_send:
                        data = {
                            'amount': transaction.amount,
                            'address': transaction.address,
                            'source': 'WatchTower',
                            'token': transaction.token.tokenid,
                            'txid': transaction.txid,
                            'block': block,
                            'spent_index': transaction.spent_index
                        }
                        
                        #check if telegram/slack 3user
                        # retrieve subscribers' channel_id to be added to payload as a list (for Slack)
                        
                        if webhook_address.address == settings.SLACK_DESTINATION_ADDR:
                            subscribers = subscription.subscriber.exclude(slack_user_details={})
                            botlist = list(subscribers.values_list('slack_user_details__channel_id', flat=True))
                            data['channel_id_list'] = json.dumps(botlist)
                            
                        if webhook_address.address == settings.TELEGRAM_DESTINATION_ADDR:
                            subscribers = subscription.subscriber.exclude(telegram_user_details={})
                            botlist = list(subscribers.values_list('telegram_user_details__id', flat=True))
                            data['chat_id_list'] = json.dumps(botlist)
                        

                        resp = requests.post(webhook_address.address,data=data)
                        if resp.status_code == 200:
                            transaction.acknowledged = True
                        elif resp.status_code == 404:
                            LOGGER.error(f"!!! ATTENTION !!! THIS IS AN INVALID DESTINATION URL: {webhook_address.address}")
                        else:
                            self.retry(countdown=3)
                transaction.save()
                return f'ACKNOWLEDGEMENT SENT FOR : {transaction.txid}'
    return


# SECOND LAYER
@shared_task(bind=True, queue='problematic_transactions')
def problematic_transactions(self):  
    if b'PENDING-BLOCKS' not in REDIS_STORAGE.keys(): REDIS_STORAGE.set('PENDING-BLOCKS', json.dumps([]))
    time_threshold = timezone.now() - datetime.timedelta(hours=2)
    blocks = BlockHeight.objects.exclude(
        problematic=[]
    ).order_by('-number')
    if blocks.exists():
        list_blocks = list(blocks.values('id','problematic', 'unparsed', 'number'))
        block = list_blocks[0]
        problematic_transactions = block['problematic']
        pending = json.loads(REDIS_STORAGE.get('PENDING-BLOCKS'))
        if not pending:
            pending.append(block['number'])
            REDIS_STORAGE.set('PENDING-BLOCKS', json.dumps(pending))
            BlockHeight.objects.filter(id=block['id']).update(
                problematic=[],
                unparsed=[]
            )                
            return f'BLOCK {block["number"]} WILL RERUN IMMEDIATELY TO PROCESS {length} PROBLEMATIC TRANSACTIONS.'
        unparsed_transactions = block['unparsed']
        
        for txn_id in block['problematic']:
            if Transaction.objects.filter(txid=txn_id).exists():
                problematic_transactions.remove(txn_id)
            else:
                break
        if not Transaction.objects.filter(txid=txn_id).exists():
            rb = RestBitcoin()
            response = rb.get_transaction(txn_id, block['id'])

            if response['status'] == 'success' and response['message'] == 'found':
                save_record.delay(*response['args'])
                problematic_transactions.remove(txn_id)
            if response['status'] == 'success' and response['message'] == 'no token':
                rb = RestBitcoin()
                args = rb.bch_checker(txn_id)
                if args:
                    if args[1] == 'unparsed':
                        unparsed_transactions.append(args[2])
                    else:
                        save_record(*args)
                    problematic_transactions.remove(txn_id)
                        
        

        
        BlockHeight.objects.filter(id=block['id']).update(
            problematic=problematic_transactions,
            unparsed=unparsed_transactions
        )
        return f'FIXING PROBLEMATIC TX: {txn_id}'
    return 'NO PROBLEMATIC TRANSACTIONS AS OF YET'

@shared_task(queue='review_block')
def review_block():
    blocks = BlockHeight.objects.exclude(transactions_count=0).filter(processed=False)
    active_block = REDIS_STORAGE.get('ACTIVE-BLOCK')
    if active_block: blocks = blocks.exclude(number=active_block)
    for block in blocks:
        found_transactions = block.transactions.distinct('txid')
    
        if block.transactions_count == len(block.problematic) + found_transactions.count() + len(block.unparsed):
            block.save()
            LOGGER.info(f'ALL TRANSACTIONS IN BLOCK {block.number} WERE COMPLETED.')
            continue

        missing = []
        db_transactions = found_transactions.values_list('txid', flat=True)


        rb = RestBitcoin()
        resp_data = rb.get_block(block.number)
        
        if 'error' not in resp_data.keys():
            transactions = resp_data['tx']
            for tr in transactions:
                if tr not in db_transactions and tr not in block.problematic:
                    missing.append(tr)
            block.problematic = list(set(missing))

            block.save()
            LOGGER.info(f'ALL TRANSACTIONS IN BLOCK {block.number} HAVE BEEN COMPLETED')

    return 'REVIEW BLOCK DONE.'


# FIRST LAYER
@shared_task(queue='save_record')
def save_record(token, transaction_address, transactionid, amount, source, blockheightid=None, spent_index=0):
    subscription = check_wallet_address_subscription(transaction_address)
    if not subscription.exists(): return 
    """
        token                : can be tokenid (slp token) or token name (bch)
        transaction_address  : the destination address where token had been deposited.
        transactionid        : transaction id generated over blockchain.
        amount               : the amount being transacted.
        source               : the layer that summoned this function (e.g SLPDB, Bitsocket, BitDB, SLPFountainhead etc.)
        blockheight          : an optional argument indicating the block height number of a transaction.
        spent_index          : used to make sure that each record is unique based on slp/bch address in a given transaction_id
    """

    try:
        spent_index = int(spent_index)
    except TypeError as exc:
        spent_index = 0

    with trans.atomic():
        try:
            if token.lower() == 'bch':
                token_obj, _ = Token.objects.get_or_create(name=token)
            else:
                token_obj, _ = Token.objects.get_or_create(tokenid=token)
            
            transaction_obj, transaction_created = Transaction.objects.get_or_create(
                txid=transactionid,
                address=transaction_address,
                token=token_obj,
                amount=amount,
                spent_index=spent_index,
                source=source
            )

            if blockheightid is not None:
                transaction_obj.blockheight_id = blockheightid
                transaction_obj.save()

                # Automatically update all transactions with block height.
                Transaction.objects.filter(txid=transactionid).update(blockheight_id=blockheightid)

            if token == 'bch':
                address_obj, created = BchAddress.objects.get_or_create(address=transaction_address)
            else:
                address_obj, created = SlpAddress.objects.get_or_create(address=transaction_address)
            
            address_obj.transactions.add(transaction_obj)
            address_obj.save()
                    
        except OperationalError as exc:
            save_record.delay(token, transaction_address, transactionid, amount, source, blockheightid, spent_index)
            return f"RETRIED SAVING/UPDATING OF TRANSACTION | {transactionid}"


@app.task(bind=True, queue='bitdbquery_transactions')
def bitdbquery_transactions(self, data):
    source = 'bitdb-query'
    block_id = REDIS_STORAGE.get('BLOCK_ID')
    total = int(REDIS_STORAGE.get('BITDBQUERY_TOTAL'))

    for transaction in data:
        tx_count = int(REDIS_STORAGE.get('BITDBQUERY_COUNT'))
        txn_id = transaction['tx']['h']
        for out in transaction['out']: 
            args = tuple()
            amount = out['e']['v'] / 100000000
            spent_index = out['e']['i']
            if 'a' in out['e'].keys():
                bchaddress = 'bitcoincash:' + str(out['e']['a'])
                args = (
                    'bch',
                    bchaddress,
                    txn_id,
                    amount,
                    source,
                    block_id,
                    spent_index
                )
                save_record(*args)
                LOGGER.info(f' * SOURCE: {source.upper()} | BLOCK {block.number} | TX: {txn_id} | BCH: {bchaddress} | {tx_count} OUT OF {total}')
        tx_count += 1
        REDIS_STORAGE.set('BITDBQUERY_COUNT', tx_count)
    
    if (total == tx_count):
        block = BlockHeight.objects.get(id=block_id)
        block.save()
        REDIS_STORAGE.set('READY', 1)
        REDIS_STORAGE.set('ACTIVE-BLOCK', '')
        review_block.delay()

@shared_task(bind=True, queue='bitdbquery')
def bitdbquery(self, block_id, max_retries=20):
    try:
        block = BlockHeight.objects.get(id=block_id)
        if block.processed: return  # Terminate here if processed already
        divider = "\n\n##########################################\n\n"
        source = 'bitdb-query'
        LOGGER.info(f"{divider}REQUESTING TO {source.upper()} | BLOCK: {block.number}{divider}")
        obj = bitdb_scanner.BitDB()
        data = obj.get_transactions_by_blk(int(block.number))
        total = len(data)
        LOGGER.info(f"{divider}{source.upper()} WILL SERVE {total} BCH TRANSACTIONS {divider}")
<<<<<<< HEAD
        REDIS_STORAGE.set('BITDBQUERY_TOTAL', total)
        REDIS_STORAGE.set('BITDBQUERY_COUNT', 0)
        bitdbquery_transactions.chunks(data, 1000).apply_async(queue='bitdbquery_transactions')
=======
        tx_count = 1
        for transaction in data:
            # Check every hundred tx if block has been processed
            if tx_count % 100 == 0:
                block = BlockHeight.objects.get(id=block_id)
                if block.processed: return

            txn_id = transaction['tx']['h']
            for out in transaction['out']: 
                args = tuple()
                amount = out['e']['v'] / 100000000
                spent_index = out['e']['i']
                if 'a' in out['e'].keys():
                    bchaddress = 'bitcoincash:' + str(out['e']['a'])
                    args = (
                        'bch',
                        bchaddress,
                        txn_id,
                        amount,
                        source,
                        block_id,
                        spent_index
                    )
                    save_record(*args)
                    LOGGER.info(f' * SOURCE: {source.upper()} | BLOCK {block.number} | TX: {txn_id} | BCH: {bchaddress} | {tx_count} OUT OF {total}')
            tx_count += 1
        block.transactions_count = tx_count
        block.save()
        REDIS_STORAGE.set('READY', 1)
        REDIS_STORAGE.set('ACTIVE-BLOCK', '')
        review_block.delay()
>>>>>>> a94b2b6143af996ee568c7d632d5825bfbccb6cf
    except bitdb_scanner.BitDBHttpException:
        self.retry(countdown=3)

@app.task(bind=True)
def slpdbquery_transactions(self, data):
    source = 'slpdb-query'
    block_id = REDIS_STORAGE.get('BLOCK_ID')
    total = int(REDIS_STORAGE.get('SLPDBQUERY_TOTAL'))
    for transaction in data:
        tx_count = int(REDIS_STORAGE.get('SLPDBQUERY_COUNT'))
        if transaction['slp']['valid']:
            spent_index = 0
            if transaction['slp']['detail']['transactionType'].lower() in ['send', 'mint', 'burn']:
                token_id = transaction['slp']['detail']['tokenIdHex']
                token, _ = Token.objects.get_or_create(tokenid=token_id)
                
                if transaction['slp']['detail']['outputs'][0]['address'] is not None:
                    for output in transaction['slp']['detail']['outputs']:
                        save_record(
                            token.tokenid,
                            output['address'],
                            transaction['tx']['h'],
                            output['amount'],
                            source,
                            blockheightid=block_id,
                            spent_index=spent_index
                        )
                        LOGGER.info(f" * SOURCE: {source.upper()} | BLOCK {block.number} | TX: {transaction['tx']['h']} | SLP: {output['address']} | {tx_count} OUT OF {total}")
                        spent_index += 1
        tx_count += 1
        REDIS_STORAGE.set('SLPDBQUERY_COUNT', tx_count)

    if (total == tx_count):
        bitdbquery.delay(block_id)


@shared_task(bind=True, queue='slpdbquery')
def slpdbquery(self, block_id):
    REDIS_STORAGE.set('BLOCK_ID', block_id)
    try:
        block = BlockHeight.objects.get(id=block_id)
        if block.processed: return  # Terminate here if processed already
        
        divider = "\n\n##########################################\n\n"
        source = 'slpdb-query'    
        LOGGER.info(f"{divider}REQUESTING TO {source.upper()} | BLOCK: {block.number}{divider}")
        time.sleep(30)
        # Sleeping is necessary to set an interval to get the complete number of transactions
        obj = slpdb_scanner.SLPDB()
        data = obj.get_transactions_by_blk(int(block.number))
        total = len(data)
        LOGGER.info(f"{divider}{source.upper()} WILL SERVE {total} SLP TRANSACTIONS {divider}")
<<<<<<< HEAD
        REDIS_STORAGE.set('SLPDBQUERY_TOTAL', total)
        REDIS_STORAGE.set('SLPDBQUERY_COUNT', 0)
        slpdbquery_transactions.chunks(data, 500)(queue='slpdbquery_transactions')
        
=======
        tx_count = 1
        for transaction in data:
            # Check every hundred tx if block has been processed
            if tx_count % 100 == 0:
                block = BlockHeight.objects.get(id=block_id)
                if block.processed: return
            
            if transaction['slp']['valid']:
                spent_index = 0
                if transaction['slp']['detail']['transactionType'].lower() in ['send', 'mint', 'burn']:
                    token_id = transaction['slp']['detail']['tokenIdHex']
                    token, _ = Token.objects.get_or_create(tokenid=token_id)
                    
                    if transaction['slp']['detail']['outputs'][0]['address'] is not None:
                        for output in transaction['slp']['detail']['outputs']:
                            save_record(
                                token.tokenid,
                                output['address'],
                                transaction['tx']['h'],
                                output['amount'],
                                source,
                                blockheightid=block_id,
                                spent_index=spent_index
                            )
                            LOGGER.info(f" * SOURCE: {source.upper()} | BLOCK {block.number} | TX: {transaction['tx']['h']} | SLP: {output['address']} | {tx_count} OUT OF {total}")
                            spent_index += 1
            tx_count += 1
        bitdbquery.delay(block_id)
>>>>>>> a94b2b6143af996ee568c7d632d5825bfbccb6cf
    except slpdb_scanner.SLPDBHttpExcetion:
        self.retry(countdown=3)


@shared_task(bind=True, queue='manage_block_transactions')
def manage_block_transactions(self):
    if b'READY' not in REDIS_STORAGE.keys(): REDIS_STORAGE.set('READY', 1)
    if b'ACTIVE-BLOCK' not in REDIS_STORAGE.keys(): REDIS_STORAGE.set('ACTIVE-BLOCK', '')
    if b'PENDING-BLOCKS' not in REDIS_STORAGE.keys(): REDIS_STORAGE.set('PENDING-BLOCKS', json.dumps([]))
    
    pending_blocks = REDIS_STORAGE.get('PENDING-BLOCKS')
    blocks = json.loads(pending_blocks)

    if not blocks: return 'NO PENDING BLOCKS'

    if int(REDIS_STORAGE.get('READY')):
        active_block = blocks[0]
        REDIS_STORAGE.set('READY', 0)
        REDIS_STORAGE.set('ACTIVE-BLOCK', active_block)
        if active_block in blocks:
            blocks.remove(active_block)
            blocks = list(set(blocks))  # Uniquify the list
            blocks.sort()  # Then sort, ascending
            pending_blocks = json.dumps(blocks)
            REDIS_STORAGE.set('PENDING-BLOCKS', pending_blocks)
        block = BlockHeight.objects.get(number=active_block)
        if block.processed:
            REDIS_STORAGE.set('READY', 1)
            REDIS_STORAGE.set('ACTIVE-BLOCK', '')
        else:
            slpdbquery.delay(block.id)
    
    active_block = str(REDIS_STORAGE.get('ACTIVE-BLOCK'))
    if active_block:
        return f'REDIS IS TOO BUSY FOR BLOCK {active_block}.'
    else:
        return 'REDIS IS WAITING FOR AN ACTIVE BLOCK. THERE HAS TO BE AN ACTIVE BLOCK RUNNING.'

@shared_task(bind=True, queue='get_latest_block')
def get_latest_block(self):
    # This task is intended to check new blockheight every 5 seconds through BitDB Query
    obj = bitdb_scanner.BitDB()
    number = obj.get_latest_block()
    obj, created = BlockHeight.objects.get_or_create(number=number)
    if created:
        return f'*** NEW BLOCK { obj.number } ***'
        
    else:
        return 'NO NEW BLOCK'

