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
import json, random
from main.utils import block_setter, check_wallet_address_subscription, check_token_subscription
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


LOGGER = logging.getLogger(__name__)
REDIS_STORAGE = settings.REDISKV

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
                    can_be_send = check_token_subscription(transaction.token.tokenid, subscription.id)
                    if can_be_send:
                        data = {
                            'amount': transaction.amount,
                            'address': transaction.address,
                            'source': transaction.source,
                            'token': transaction.token.tokenid,
                            'txid': transaction.txid,
                            'block': block,
                            'spent_index': transaction.spent_index
                        }
                        
                        #check if telegram/slack user
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
                            response_data = json.loads(resp.text)
                            if response_data['success']:
                                transaction.acknowledged = True
                        elif resp.status_code == 404:
                            LOGGER.error(f"!!! ATTENTION !!! THIS IS AN INVALID DESTINATION URL: {webhook_address.address}")
                        else:
                            self.retry(countdown=3)
                transaction.save()
                return f'ACKNOWLEDGEMENT SENT FOR : {txid}'
    return


# SECOND LAYER
@shared_task(bind=True, queue='problematic_transactions')
def problematic_transactions(self):  
    time_threshold = timezone.now() - datetime.timedelta(hours=2)
    blocks = BlockHeight.objects.exclude(
        problematic=[]
    ).order_by('-number')
    if blocks.exists():
        blocks = list(blocks.values('id','problematic'))
        block = blocks[0]
        problematic_transactions = block['problematic']
        txn_id = problematic_transactions[0]
        if not Transaction.objects.filter(txid=txn_id).exists():
            rb = RestBitcoin()
            response = rb.get_transaction(txn_id, block['id'])

            if response['status'] == 'success' and response['message'] == 'found':
                save_record.delay(*response['args'])
                problematic_transactions.remove(txn_id)
            if response['status'] == 'success' and response['message'] == 'no token':
                rb = RestBitcoin()
                msg = rb.bch_checker(txn_id)
                if 'PROCESSED VALID' in msg: problematic_transactions.remove(txn_id)    
        else:
            problematic_transactions.remove(txn_id)

        BlockHeight.objects.filter(id=block['id']).update(problematic=problematic_transactions)
        return f'FIXING PROBLEMATIC TX: {txn_id}'
    return 'NO PROBLEMATIC TRANSACTIONS AS OF YET'

@shared_task(queue='review_block')
def review_block():
    blocks = BlockHeight.objects.exclude(transactions_count=0).filter(processed=False)
    active_block = REDIS_STORAGE.get('ACTIVE-BLOCK')
    if active_block: blocks = blocks.exclude(number=active_block)
    for block in blocks:
        found_transactions = block.transactions.distinct('txid')
    
        if block.transactions_count == len(block.problematic) + found_transactions.count():
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

@shared_task(bind=True, queue='bitdbquery')
def bitdbquery(self, block_id): 
    divider = "\n\n##########################################\n\n"
    source = 'bitdb-query'
    LOGGER.info(f"{divider}REQUESTING TO {source.upper()}{divider}")
    block = BlockHeight.objects.get(id=block_id)
    obj = bitdb_scanner.BitDB()
    data = obj.get_transactions_by_blk(int(block.number))
    total = len(data)
    block.transactions_count = total
    block.save()
    LOGGER.info(f"{divider}{source.upper()} WILL SERVE {total} BCH TRANSACTIONS {divider}")
    tx_count = 1
    for transaction in data:
        txn_id = transaction['tx']['h']
        LOGGER.info(f' * SOURCE: {source.upper()} | BLOCK {block.number} | TX: {txn_id} | {tx_count} OUT OF {total}')
        counter = 1
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
            counter += 1
        tx_count += 1
    REDIS_STORAGE.set('READY', 1)
    REDIS_STORAGE.set('ACTIVE-BLOCK', '')
    review_block.delay()

@shared_task(bind=True, queue='slpdbquery')
def slpdbquery(self, block_id):
    divider = "\n\n##########################################\n\n"
    source = 'slpdb-query'    
    LOGGER.info(f"{divider}REQUESTING TO {source.upper()}{divider}")
    block = BlockHeight.objects.get(id=block_id)
    obj = slpdb_scanner.SLPDB()
    data = obj.get_transactions_by_blk(int(block.number))
    total = len(data)
    LOGGER.info(f"{divider}{source.upper()} WILL SERVE {total} SLP TRANSACTIONS {divider}")
    tx_count = 1
    for transaction in data:
        LOGGER.info(f" * SOURCE: {source.upper()} | BLOCK {block.number} | TX: {transaction['tx']['h']} | {tx_count} OUT OF {total}")
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
                        LOGGER.info(f"{transaction['tx']['h']} : {source.upper()}")
                        spent_index += 1
        tx_count += 1
    bitdbquery.delay(block_id)
   
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
            pending_blocks = json.dumps(blocks)
        block = BlockHeight.objects.get(number=active_block)
        slpdbquery.delay(block.id)
        REDIS_STORAGE.set('PENDING-BLOCKS', pending_blocks)

    return 'REDIS IS TOO BUSY TO PROCESS NEW BLOCK'

@shared_task(queue='get_latest_block')
def get_latest_block():
    # This task is intended to check new blockheight every 5 seconds through REST.BITCOIN.COM.
    if b'ACTIVE-BLOCK' not in REDIS_STORAGE.keys(): REDIS_STORAGE.set('ACTIVE-BLOCK', '')
    proceed = False
    url = 'https://rest.bitcoin.com/v2/blockchain/getBlockchainInfo'
    try:
        resp = requests.get(url)
    except Exception as exc:
        return LOGGER.error(exc)
    
    if not 'blocks' in resp.text: return f"INVALID RESPONSE FROM  {url} : {resp.text}"
    number = json.loads(resp.text)['blocks']

    obj, created = BlockHeight.objects.get_or_create(number=number)
    if created:
        # Queue to "PENDING-BLOCKS"
        added, neglected = block_setter(number, new=True)
        if added:
            limit = obj.number - settings.MAX_BLOCK_AWAY
            BlockHeight.objects.filter(number__lte=limit).delete()
            if neglected:
                review_block.delay()
            return f'*** NEW BLOCK { number } ***'
    else:
        return 'NO NEW BLOCK'

