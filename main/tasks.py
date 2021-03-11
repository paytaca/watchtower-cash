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
from main.utils import missing_blocks, block_setter, check_wallet_address_subscription, check_token_subscription
from main.utils import slpdb as slpdb_scanner
from main.utils.spicebot_token_registration import SpicebotTokens
from main.utils.restbitcoin import RestBitcoin
from django.conf import settings
import traceback, datetime
from sseclient import SSEClient
from django.db import transaction as trans
import base64
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


# MAIN SOURCES OF BCH/SLP TRANSACTIONS
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
            response = rb.get_transaction(txn_id, block['id'], 0)

            if response['status'] == 'success' and response['message'] == 'found':
                save_record.delay(*response['args'])
                problematic_transactions.remove(txn_id)
            if response['status'] == 'success' and response['message'] == 'no token':
                msg = bch_checker(txn_id)
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
    if active_block:
        blocks = blocks.exclude(number=active_block)
    for block in blocks:
        block = blocks.first()
        found_transactions = block.transactions.distinct('txid')
        if block.transactions_count == len(block.genesis) + len(block.problematic) + found_transactions.count():
            block.save()
            return 'ALL TRANSACTIONS ARE ALREADY COMPLETE'
        missing = []
        db_transactions = found_transactions.values_list('txid', flat=True)
        url = f'https://rest.bitcoin.com/v2/block/detailsByHeight/{block.number}'
        resp = requests.get(url)
        if resp.status_code == 200:
            resp_data = json.loads(resp.text)
            problematic_trx = (block.problematic)
            if 'error' not in resp_data.keys():
                transactions = resp_data['tx']
                for tr in transactions:
                    if tr not in db_transactions and tr not in block.genesis and tr not in block.problematic:
                        missing.append(tr)
                problematic_trx += missing
                block.problematic = list(set(problematic_trx))
                block.save()
                return 'ALL TRANSACTIONS HAVE BEEN COMPLETED'
    return 'ALL BLOCKS ARE UPDATED.'

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

@shared_task(bind=True, queue='redis_writer')
def redis_writer(self, value, key, action):
    key = key.upper()
    if action == "append":
        container = REDIS_STORAGE.get(key)
        if container:
            redis_container = json.loads(container)
            redis_container.append(value)
            REDIS_STORAGE.set(key, json.dumps(redis_container))
    return f"{key} TRANSACTION: {value}"

@shared_task(bind=True, queue='save_record')
def postgres_writer(self, blockheight_id,  genesis, problematic):
    with trans.atomic():
        obj = BlockHeight.objects.get(id=blockheight_id)
        new_genesis = obj.genesis + genesis
        all_genesis = list(set(new_genesis))
        all_problematic = obj.problematic + problematic
        all_transactions = obj.transactions.distinct('txid').values_list('txid', flat=True)
        obj.problematic = [tr for tr in list(set(all_problematic)) if tr not in all_transactions]
        obj.problematic = [tr for tr in obj.problematic if tr not in obj.genesis]
        obj.genesis = [tr for tr in list(set(all_genesis)) if tr not in all_transactions]
        obj.save()
    return None

def bch_checker(txn_id):
    url = f'https://rest.bitcoin.com/v2/transaction/details/{txn_id}'
    
    proceed = False
    try:
        response = requests.get(url)
        if response.status_code == 200: proceed = True
    except Exception as exc:
        return f"PROBLEMATIC TX: {txn_id}"
    if proceed:
        data = json.loads(response.text)
        if 'blockheight' in data.keys():
            blockheight_obj, created = BlockHeight.objects.get_or_create(number=data['blockheight'])
            if 'vout' in data.keys():
                for out in data['vout']:
                    if 'scriptPubKey' in out.keys():
                        if 'cashAddrs' in out['scriptPubKey'].keys():
                            for cashaddr in out['scriptPubKey']['cashAddrs']:
                                if cashaddr.startswith('bitcoincash:'):
                                    save_record.delay(
                                        'bch',
                                        cashaddr,
                                        data['txid'],
                                        out['value'],
                                        "bch_checker",
                                        blockheightid=blockheight_obj.id,
                                        spent_index=out['spentIndex']
                                    )
                                    return f"PROCESSED VALID BCH TX: {txn_id}"
                        else:
                            # A transaction has no cash address:
                            save_record.delay(
                                'bch',
                                'unparsed',
                                data['txid'],
                                out['value'],
                                "bch_checker",
                                blockheightid=blockheight_obj.id,
                                spent_index=out['spentIndex']
                            )
                            return f"PROCESSED VALID BCH TX: {txn_id}"

    return f"PROCESSED BCH TX: {txn_id}"

@shared_task(bind=True, queue='transaction_filter', max_retries=2)
def transaction_filter(self, txn_id, blockheightid, currentcount, total_transactions):
    obj = BlockHeight.objects.get(id=blockheightid)
    """
    Tracks every transactions that belongs to the registered token and blockheight.
    """
    
    rb = RestBitcoin()
    response = rb.get_transaction(txn_id, blockheightid, currentcount)

    if response['status'] == 'success' and response['message'] == 'found':
        save_record.delay(*response['args'])

    if response['status'] == 'success' and response['message'] == 'no token':
        bch_checker(txn_id)
        
    if response['status'] == 'success' and response['message'] == 'genesis':
        redis_writer.delay(txn_id, 'genesis', "append")

    
    
    if int(total_transactions) == int(currentcount):
        active_transactions = json.loads(REDIS_STORAGE.get('ACTIVE-BLOCK-TRANSACTIONS'))
        genesis = json.loads(REDIS_STORAGE.get('GENESIS'))
        
        missing = [tr for tr in active_transactions if not Transaction.objects.filter(txid=tr).exists()]
        problematic = [tr for tr in missing if tr not in genesis]
        postgres_writer.delay(obj.id, genesis, problematic)

        if int(REDIS_STORAGE.get('ACTIVE-BLOCK-TRANSACTIONS-INDEX-LIMIT')) == int(REDIS_STORAGE.get('ACTIVE-BLOCK-TRANSACTIONS-CURRENT-INDEX')):
            REDIS_STORAGE.delete('ACTIVE-BLOCK')
            REDIS_STORAGE.delete('ACTIVE-BLOCK-TRANSACTIONS')
            REDIS_STORAGE.delete('ACTIVE-BLOCK-TRANSACTIONS-CURRENT-INDEX')
            REDIS_STORAGE.delete('ACTIVE-BLOCK-TRANSACTIONS-INDEX-LIMIT')
            REDIS_STORAGE.delete('ACTIVE-BLOCK-TRANSACTIONS-COUNT')
            REDIS_STORAGE.delete('GENESIS')
            REDIS_STORAGE.delete('READY')
            LOGGER.info(f"DONE CHECKING {blockheightid}.")

        elif int(REDIS_STORAGE.get('ACTIVE-BLOCK-TRANSACTIONS-INDEX-LIMIT')) > int(REDIS_STORAGE.get('ACTIVE-BLOCK-TRANSACTIONS-CURRENT-INDEX')):
        

            REDIS_STORAGE.delete('ACTIVE-BLOCK-TRANSACTIONS')
            REDIS_STORAGE.delete('GENESIS')

            current_index = int(REDIS_STORAGE.get('ACTIVE-BLOCK-TRANSACTIONS-CURRENT-INDEX'))
            current_index += 1

            REDIS_STORAGE.set('ACTIVE-BLOCK-TRANSACTIONS-CURRENT-INDEX', current_index)
            REDIS_STORAGE.set('READY', 1)

            LOGGER.info(f"DONE CHECKING CHUNK INDEX {current_index}: {total_transactions} TXS")


    return f"{currentcount} out of {total_transactions} : {response['status']} : {txn_id}"

@shared_task( bind=True, queue='get_block_transactions')
def get_block_transactions(self):
    if b'ACTIVE-BLOCK-TRANSACTIONS' not in REDIS_STORAGE.keys(): REDIS_STORAGE.set('ACTIVE-BLOCK-TRANSACTIONS', json.dumps([]))
    if b'ACTIVE-BLOCK' not in REDIS_STORAGE.keys(): REDIS_STORAGE.set('ACTIVE-BLOCK', '')
    if b'READY' not in REDIS_STORAGE.keys(): REDIS_STORAGE.set('READY', 1)
    if b'GENESIS' not in REDIS_STORAGE.keys(): REDIS_STORAGE.set('GENESIS', json.dumps([]))

    
    active_block_transactions = REDIS_STORAGE.get('ACTIVE-BLOCK-TRANSACTIONS')
    transactions = json.loads(active_block_transactions)
    active_block = REDIS_STORAGE.get('ACTIVE-BLOCK')
    ready = int(REDIS_STORAGE.get('READY'))

    if active_block and transactions and ready:
        REDIS_STORAGE.set('READY', 0)
        active_block = int(active_block)
        block = BlockHeight.objects.get(number=active_block)
        total_chunk_transactions = len(transactions)
        counter = 1
        for tr in transactions:
            transaction_filter.delay(
                tr,
                block.id,
                counter,
                total_chunk_transactions
            )
            counter += 1
            LOGGER.info(f"FETCHING TRANSACTION {tr} IN BLOCK {active_block}")
        return f"DEPLOYED {total_chunk_transactions} TRANSACTIONS OF BLOCK {active_block}."
    else:
        return f"NO NEW BLOCK TRANSACTIONS."

@shared_task(bind=True, queue='manage_block_transactions')
def manage_block_transactions(self):
    if b'READY' not in REDIS_STORAGE.keys(): REDIS_STORAGE.set('READY', 1)
    if b'ACTIVE-BLOCK' not in REDIS_STORAGE.keys(): REDIS_STORAGE.set('ACTIVE-BLOCK', '')
    if b'ACTIVE-BLOCK-TRANSACTIONS-CURRENT-INDEX' not in REDIS_STORAGE.keys(): REDIS_STORAGE.set('ACTIVE-BLOCK-TRANSACTIONS-CURRENT-INDEX', 0)
    if b'PENDING-BLOCKS' not in REDIS_STORAGE.keys(): REDIS_STORAGE.set('PENDING-BLOCKS', json.dumps([]),)
    if b'GENESIS' not in REDIS_STORAGE.keys(): REDIS_STORAGE.set('GENESIS', json.dumps([]))
    if b'ACTIVE-BLOCK-TRANSACTIONS-COUNT' not in REDIS_STORAGE.keys(): REDIS_STORAGE.set('ACTIVE-BLOCK-TRANSACTIONS-COUNT', 0)
    

    pending_blocks = REDIS_STORAGE.get('PENDING-BLOCKS')
    blocks = json.loads(pending_blocks)
    if len(blocks) == 0 and not REDIS_STORAGE.get('ACTIVE-BLOCK'): return 'NO PENDING BLOCKS'
    if not REDIS_STORAGE.get('ACTIVE-BLOCK'): REDIS_STORAGE.set('ACTIVE-BLOCK', blocks[0])
    active_block = int(REDIS_STORAGE.get('ACTIVE-BLOCK'))

    if active_block and int(REDIS_STORAGE.get('READY')):
        if active_block in blocks:
            blocks.remove(active_block)
            pending_blocks = json.dumps(blocks)

        # REST.BITCOIN.COM
        LOGGER.info(f'FETCHING DETAILS IN BLOCK {active_block} via REST.BITCOIN.COM')
        url = 'https://rest.bitcoin.com/v2/block/detailsByHeight/%s' % active_block
        resp = requests.get(url)
        if resp.status_code == 200:
            resp_data = json.loads(resp.text)
            if 'error' not in resp_data.keys():
                transactions = resp_data['tx']
                total_transactions = len(transactions)
                BlockHeight.objects.filter(
                    number=active_block
                ).update(
                    transactions_count=total_transactions
                )
                REDIS_STORAGE.set('PENDING-BLOCKS', pending_blocks)
                REDIS_STORAGE.set('ACTIVE-BLOCK-TRANSACTIONS-COUNT', total_transactions)

                transaction_index = int(REDIS_STORAGE.get('ACTIVE-BLOCK-TRANSACTIONS-CURRENT-INDEX'))
                counter = 0
                for i in range(0, total_transactions, settings.MAX_BLOCK_TRANSACTIONS): 
                    chunk = transactions[i:i + settings.MAX_BLOCK_TRANSACTIONS]
                    if counter == transaction_index:
                        REDIS_STORAGE.set('ACTIVE-BLOCK-TRANSACTIONS', json.dumps(chunk))

                    counter += 1
                REDIS_STORAGE.set('ACTIVE-BLOCK-TRANSACTIONS-INDEX-LIMIT', counter-1)
                get_block_transactions.delay()
                return f'READY TO REVIEW TRANSACTIONS CHUNK'
            else:
                return 'FAILED'
        else:
            return f'{resp.text.upper()}'
    return 'REDIS IS TOO BUSY TO ACCEPT NEW TRANSACTIONS CHUNK'

@shared_task(queue='get_latest_block')
def get_latest_block():
    if b'ACTIVE-BLOCK' not in REDIS_STORAGE.keys('*'): REDIS_STORAGE.set('ACTIVE-BLOCK', '')
    if b'REST-BITCOIN-RETRIES' not in REDIS_STORAGE.keys(): REDIS_STORAGE.set('REST-BITCOIN-RETRIES', 0)
    # A task intended to check new blockheight every 5 seconds.
    proceed = False
    url = 'https://rest.bitcoin.com/v2/blockchain/getBlockchainInfo'
    try:
        resp = requests.get(url)
        REDIS_STORAGE.set('REST-BITCOIN-RETRIES', 0)
    except Exception as exc:
        retry = int(REDIS_STORAGE.get('REST-BITCOIN-RETRIES')) + 1
        REDIS_STORAGE.set('REST-BITCOIN-RETRIES', retry)
        return LOGGER.error(exc)
    
    if not 'blocks' in resp.text:
        retry = int(REDIS_STORAGE.get('REST-BITCOIN-RETRIES')) + 1
        REDIS_STORAGE.set('REST-BITCOIN-RETRIES', retry)
        return f"INVALID RESPONSE FROM  {url} : {resp.text}"
    number = json.loads(resp.text)['blocks']

    obj, created = BlockHeight.objects.get_or_create(number=number)
    if created or obj.transactions_count == 0:
        # Queue to "PENDING-BLOCKS"
        added = block_setter(number, new=True)
        if added:
            limit = obj.number - settings.MAX_BLOCK_AWAY
            BlockHeight.objects.filter(number__lte=limit).delete()
            return f'*** NEW BLOCK { number } ***'
    else:
        return 'NO NEW BLOCK'
    

# ALTERNATIVE SOURCES OF BCH/SLP TRANSACTIONS
@shared_task(bind=True, queue='bitdbquery')
def bitdbquery(self): 
    if b'REST-BITCOIN-RETRIES' not in REDIS_STORAGE.keys(): REDIS_STORAGE.set('REST-BITCOIN-RETRIES', 0)
    retry = int(REDIS_STORAGE.get('REST-BITCOIN-RETRIES'))
    if retry <= settings.MAX_RESTB_RETRIES: return 'REST.BITCOIN.COM DOES NOT NEED BITDBQUERY THIS TIME.'

    source = 'bitdb-query'
    BITDB_URL = 'https://bitdb.fountainhead.cash/q/'
    query = {
        "v": 3,
        "q": {
            "find": {
            },
            "limit": 500
        }
    }
    json_string = bytes(json.dumps(query), 'utf-8')
    url = base64.b64encode(json_string)
    resp = requests.get(BITDB_URL + url.decode('utf-8'))
    data = resp.json()
    for row in data['u']:
        txn_id = row['tx']['h']
        counter = 1
        for out in row['out']: 
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
                    None,
                    spent_index
                )
                # For intant recording of transaction, its better not to delay.
                if not Transaction.objects.filter(txid=txn_id).exists():
                    save_record.delay(*args)
            counter += 1

@shared_task(bind=True, queue='slpdbquery')
def slpdbquery(self):
    if b'REST-BITCOIN-RETRIES' not in REDIS_STORAGE.keys(): REDIS_STORAGE.set('REST-BITCOIN-RETRIES', 0)
    rb_retry = int(REDIS_STORAGE.get('REST-BITCOIN-RETRIES'))
    if rb_retry <= settings.MAX_RESTB_RETRIES : return 'REST.BITCOIN.COM DOES NOT NEED SLPDBQUERY THIS TIME.'

    obj = slpdb_scanner.SLPDB()
    try:
        data = obj.process_api()
        proceed_slpdb_checking = True
    except Exception as exc:
        LOGGER.error(exc)
        proceed_slpdb_checking = False

    if data['status'] == 'success' and proceed_slpdb_checking:
        source = 'slpdb-query'
        LOGGER.info(f'LOOKING FOR RECENT SLP TRANSACTIONS THROUGH SLPDB')
        transactions = data['data']['c']

        for transaction in transactions:
            blocknumber = transaction['blk']['i']
            block = BlockHeight.objects.first()
            if block.number > blocknumber: return f'{source.upper()} : OLD BLOCK : {blocknumber}'
            if transaction['slp']['valid']:
                if transaction['slp']['detail']['transactionType'].lower() == 'send':
                    token_id = transaction['slp']['detail']['tokenIdHex']
                    token, _ = Token.objects.get_or_create(tokenid=token_id)
                    if transaction['slp']['detail']['outputs'][0]['address'] is not None:
                        spent_index = 0
                        for output in transaction['slp']['detail']['outputs']:
                            if not Transaction.objects.filter(txid=transaction['tx']['h']).exists():
                                save_record.delay(
                                    token.tokenid,
                                    output['address'],
                                    transaction['tx']['h'],
                                    output['amount'],
                                    source,
                                    blockheightid=block.id,
                                    spent_index=spent_index
                                )
                                LOGGER.info(f"{transaction['tx']['h']} : {source.upper()}")
                            spent_index += 1