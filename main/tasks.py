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

import json, random
from main.utils import slpdb, missing_blocks, block_setter, check_wallet_address_subscription, check_token_subscription
from main.utils.spicebot_token_registration import SpicebotTokens
from main.utils.restbitcoin import RestBitcoin
from django.conf import settings
import traceback, datetime
from sseclient import SSEClient
LOGGER = logging.getLogger(__name__)
from django.db import transaction as trans
import base64
import sseclient
from django.db import OperationalError
from psycopg2.extensions import TransactionRollbackError
from django.db.utils import IntegrityError
from django.utils import timezone
from django.db.models import Q


# @shared_task(bind=True, queue='client_acknowledgement', max_retries=3)
# def client_acknowledgement(self, token, transactionid):
#     txn_check = Transaction.objects.filter(id=transactionid)
#     retry = False

#     if txn_check.exists():
#         txn = txn_check.first()
#         block = None
#         if txn.blockheight:
#             block = txn.blockheight.number

#         address = txn.address 
#         subscription = check_wallet_address_subscription(address)

#         if subscription.exists():
#             txn.subscribed = True
#             subscription = subscription.first()
#             webhook_addresses = subscription.address.all()

#             if webhook_addresses.count() == 0:
#                 # If subscription found yet no webhook url found,
#                 # We'll assign the webhook url for spicebot.
#                 sendto_obj = SendTo.objects.first()
#                 subscription.address.add(sendto_obj)
#                 webhook_addresses = [sendto_obj]
                
#             for webhook_address in webhook_addresses:
#                 # check subscribed Token and Token from transaction if matched.
#                 valid, token_obj = check_token_subscription(token, subscription.token.id)
#                 if valid:
#                     data = {
#                         'amount': txn.amount,
#                         'address': txn.address,
#                         'source': txn.source,
#                         'token': token_obj.tokenid,
#                         'txid': txn.txid,
#                         'block': block,
#                         'spent_index': txn.spentIndex
#                     }

#                     #check if telegram/slack user
#                     # retrieve subscribers' channel_id to be added to payload as a list (for Slack)
                    
#                     if webhook_address.address == settings.SLACK_DESTINATION_ADDR:
#                         subscribers = subscription.subscriber.exclude(slack_user_details={})
#                         botlist = list(subscribers.values_list('slack_user_details__channel_id', flat=True))
#                         data['channel_id_list'] = json.dumps(botlist)
                        
#                     if webhook_address.address == settings.TELEGRAM_DESTINATION_ADDR:
#                         subscribers = subscription.subscriber.exclude(telegram_user_details={})
#                         botlist = list(subscribers.values_list('telegram_user_details__id', flat=True))
#                         data['chat_id_list'] = json.dumps(botlist)
                    

#                     resp = requests.post(webhook_address.address,data=data)
#                     if resp.status_code == 200:
#                         response_data = json.loads(resp.text)
#                         if response_data['success']:
#                             txn.acknowledged = True
#                             txn.queued = False
#                     elif resp.status_code == 404:
#                         LOGGER.error(f'this is no longer valid > {webhook_address}')
#                     else:
#                         retry = True
#                         txn.acknowledged = False
#             txn.save()
#         else:
#             retry = True
#     if retry:
#         self.retry(countdown=180)
#     else:
#         return 'success'

@shared_task(queue='save_record')
def save_record(token, transaction_address, transactionid, amount, source, blockheightid=None, spent_index=0):
    msg = f'| SAVE RECORD TASK : {transactionid}'
    """
        token                : can be tokenid (slp token) or token name (bch)
        transaction_address  : the destination address where token had been deposited.
        transactionid        : transaction id generated over blockchain.
        amount               : the amount being transacted.
        source               : the layer that summoned this function (e.g SLPDB, Bitsocket, BitDB, SLPFountainhead etc.)
        blockheight          : an optional argument indicating the block height number of a transaction.
        spent_index          : used to make sure that each record is unique based on slp/bch address in a given transaction_id
    """
    # with_existing_trans = Transaction.objects.filter(txid=transactionid).first()
    # if with_existing_trans:
    #     if with_existing_trans.source != source:
    #         return f"Transaction {with_existing_trans.txid} was already processed by {with_existing_trans.source}."

    try:
        spent_index = int(spent_index)
    except TypeError as exc:
        spent_index = 0
    
    msg += f'| SPENT_INDEX {spent_index}'

    with trans.atomic():
        try:
            token_obj = Token.objects.get(tokenid=token)
        except Token.DoesNotExist:
            token_obj = Token.objects.get(name=token)
        msg += f'| TOKEN: {token_obj.name}'
        
        transaction_obj, transaction_created = Transaction.objects.get_or_create(
            txid=transactionid,
            address=transaction_address,
            token=token_obj,
            amount=amount,
            spentIndex=spent_index
        )
        
        if not transaction_obj.source:
            # try:
            #     Transaction.objects.filter(id=transaction_obj.id).update(source=source)
            # except Exception as exc:
            #     LOGGER.error('Operational Error while updating transaction source')
            transaction_obj.source = source
        msg += f'| SOURCE: {source}'

        if blockheightid is not None:
            # try:
            #     Transaction.objects.filter(id=transaction_obj.id).update(blockheight_id=blockheightid)
            # except Exception as exc:
            #     LOGGER.error('Operational Error while updating transaction blockheight')
            transaction_obj.blockheight_id = blockheightid

        try:
            transaction_obj.save()
        except (OperationalError, IntegrityError) as e:
            if e.__cause__.__class__ == TransactionRollbackError:
                save_record.delay(token, transaction_address, transactionid, amount, source, blockheightid, spent_index)
                return f"Retried saving of transaction | {transactionid}"
            else:
                raise
        
        try:
            if transaction_obj.blockheight is not None:
                msg += f'| BLOCKHEIGHT: {transaction_obj.blockheight.number}'
        except BlockHeight.DoesNotExist:
            pass

        if token == 'bch':
            address_obj, created = BchAddress.objects.get_or_create(address=transaction_address)
        else:
            address_obj, created = SlpAddress.objects.get_or_create(address=transaction_address)
        
        try:
            address_obj.transactions.add(transaction_obj)
            address_obj.save()
        except OperationalError as exc:
            if hasattr(exc, 'message'):
                LOGGER.error(exc.message)
            else:
                LOGGER.error(exc)
        
        if transaction_created:
            LOGGER.info(f'FINISHED!!!!! {transaction_obj.id }')
            # client_acknowledgement.delay(transaction_obj.token.tokenid, transaction_obj.id)
        LOGGER.info(msg)


@shared_task(queue='deposit_filter')
def deposit_filter(txn_id, blockheightid, currentcount, total_transactions):
    redis_storage = settings.REDISKV
    obj = BlockHeight.objects.get(id=blockheightid)
    """
    Tracks every transactions that belongs to the registered token and blockheight.
    """
    # If txn_id is already in db, we'll just update its blockheight 
    # To minimize send request on rest.bitcoin.com
    qs = Transaction.objects.filter(txid=txn_id)
    if qs.exists():
        instance = qs.first()
        if not instance.amount or not instance.source:
            Transaction.objects.filter(txid=txn_id).update(scanning=False)
            BlockHeight.objects.filter(id=blockheightid).update(currentcount=currentcount)                
            return 'success'
    obj = RestBitcoin()
    response = obj.get_transaction(txn_id, blockheightid, currentcount)
    if response['status'] == 'success' and response['message'] == 'found':
        save_record.delay(*response['args'])
    if response['status'] == 'success' and response['message'] == 'no token':
        checktransaction.delay(txn_id)
    if total_transactions == currentcount:
        redis_storage.set('READY', 1)
    return f" {response['status']} : {txn_id}"

# @shared_task(queue='slpdb_token_scanner')
# def slpdb_token_scanner():
    # tokens = Token.objects.all()
    # for token in tokens:
    #     obj = slpdb.SLPDB()
    #     data = obj.process_api(**{'tokenid': token.tokenid})
    #     if data['status'] == 'success':
    #         for transaction in data['data']['c']:
    #             if transaction['tokenDetails']['valid']:
    #                 required_keys = transaction.keys()
    #                 tx_exists = 'txid' in required_keys
    #                 token_exists = 'tokenDetails' in required_keys
    #                 blk_exists = 'blk' in required_keys
    #                 if  tx_exists and token_exists and blk_exists:
    #                     tokenid = transaction['tokenDetails']['detail']['tokenIdHex']
    #                     tokenqs = Token.objects.filter(tokenid=tokenid)
    #                     if tokenqs.exists():
    #                         # Block 625228 is the beginning...
    #                         # if transaction['blk'] >= 625228:
    #                         if transaction['blk'] >= 625190:    
    #                             token_obj = tokenqs.first()
    #                             block, created = BlockHeight.objects.get_or_create(number=transaction['blk'])
    #                             if created:
    #                                 first_blockheight_scanner.delay(block.id)
    #                             transaction['tokenDetails']['detail']['outputs'].pop(-1)
    #                             spent_index = 1
    #                             for trans in transaction['tokenDetails']['detail']['outputs']:
    #                                 amount = trans['amount']
    #                                 slpaddress = trans['address']
    #                                 args = (
    #                                     token_obj.tokenid,
    #                                     slpaddress,
    #                                     transaction['txid'],
    #                                     amount,
    #                                     "slpdb_token_scanner",
    #                                     block.id,
    #                                     spent_index
    #                                 )
    #                                 save_record(*args)
    #                                 spent_index += 1



@shared_task(queue='get_latest_block')
def get_latest_block():    
    # A task intended to check new blockheight every 5 seconds.
    proceed = False
    url = 'https://rest.bitcoin.com/v2/blockchain/getBlockchainInfo'
    try:
        resp = requests.get(url)
    except Exception as exc:
        return LOGGER.error(exc)

    number = json.loads(resp.text)['blocks']
    obj, created = BlockHeight.objects.get_or_create(number=number)
    if created:
        LOGGER.info(f'===== NEW BLOCK { number } =====')
        # Block setter sets block in REDIS
        block_setter(number, new=True)
        # bitcoincash_tracker.delay(obj.id)
    else:
        # If there's any missed/unprocessed block due to rest.bitcoin downtime,
        # There would be backward scanning of blocks.
        blocks = list(BlockHeight.objects.all().order_by('number').values_list('number',flat=True))
        blocks = list(missing_blocks(blocks,0,len(blocks)-1))
        event = 'missed'
        if not len(blocks):
            blocks = list(BlockHeight.objects.filter(processed=False).order_by('-number').values_list('number', flat=True))
            event = 'unprocessed'
        if len(blocks):
            number = blocks[-1]
            # Block setter sets block in REDIS
            added = block_setter(number, new=False)
            if added:
                obj, created = BlockHeight.objects.get_or_create(number=number)
                # bitcoincash_tracker.delay(obj.id)   
                LOGGER.info(f'===== { event.upper() } BLOCK { number } =====')
    

@shared_task(bind=True, queue='manage_block_transactions')
def manage_block_transactions(self, max_retries=3):
    redis_storage = settings.REDISKV
    blocks = json.loads(redis_storage.get('PENDING-BLOCKS'))

    if len(blocks) == 0:
        return 'success'

    block_height = blocks[0]
    blockheight_instance = BlockHeight.objects.get(number=block_height)
    blocks.remove(block_height)
    data = json.dumps(blocks)
    redis_storage.set('PENDING-BLOCKS', data)
    if not redis_storage.get('ACTIVE_BLOCK'):
        redis_storage.set('ACTIVE-BLOCK', block_height)

        # REST.BITCOIN.COM
        LOGGER.info(f'CHECKING BLOCK {block_height} via REST.BITCOIN.COM')
        url = 'https://rest.bitcoin.com/v2/block/detailsByHeight/%s' % block_height
        resp = requests.get(url)
        if resp.status_code == 200:
            data = json.loads(resp.text)
            if 'error' not in data.keys():
                transactions = data['tx']
                target_transactions = []
                done_scanning_block = True
                for tr in transactions:
                    transaction_stored = Transaction.objects.filter(txid=tr)
                    if not transaction_stored.exists():
                        target_transactions.append(tr)
                        done_scanning_block = False
                if not done_scanning_block:
                    transactions_to_process = target_transactions[0:settings.MAX_BLOCK_TRANSACTIONS]
                    redis_storage.set("ACTIVE-BLOCK-TRANSACTIONS", json.dumps(transactions_to_process))
                else:
                    # done checking all transactions in a block
                    redis_storage.set('ACTIVE-BLOCK', '')
            else:
                self.retry(countdown=120)
        else:
            self.retry(countdown=120)

@shared_task(bind=True, queue='get_block_transactions')
def get_block_transactions(self):
    redis_storage = settings.REDISKV
    active_blocks_transactions = redis_storage.get('ACTIVE-BLOCK-TRANSACTIONS')
    active_block = redis_storage.get('ACTIVE_BLOCK')
    
    if b'READY' not in redis_storage.keys():
        redis_storage.set('READY', 1)

    ready = int(redis_storage.get('READY'))
    if active_block and active_blocks_transactions and ready:
        redis_storage.set('READY', 0)
        block = BlockHeight.objects.get(number=active_block)
        if not active_blocks_transactions:
            return 'success'
        transactions = json.loads(active_blocks_transactions)
        total_transactions = len(transactions)
        counter = 1
        for tr in transactions:
            deposit_filter.delay(
                txn_id,
                block.id,
                counter,
                total_transactions
            )   
            counter += 1
            LOGGER.info(f"  =======  PROCESSED BLOCK {active_block}   =======  ")
    elif active_blocks_transactions:
        LOGGER.info(f"  =======  PROCESSING BLOCK {active_block}   =======  ")
    else:
        LOGGER.info(f"  =======  NO BLOCKS FOUND   =======  ")


# @shared_task(bind=True, queue='slpdb', max_retries=10)
# def slpdb(self, block_num=None):
#     if block_num is None:
#         redis_storage = settings.REDISKV
#         blocks = json.loads(redis_storage.get('PENDING-BLOCKS'))
#         if len(blocks) == 0:
#             return 'success'
#         number = blocks[0]
#         block_instance = BlockHeight.objects.get(number=number)
#         blocks.remove(number)
#         data = json.dumps(blocks)
#         redis_storage.set('PENDING-BLOCKS', data)
#     else:
#         block_instance = BlockHeight.objects.get(number=block_num)

#     block_height = block_instance.number
#     block_instance.processed = False
#     block_instance.save()

#     obj = slpdb.SLPDB()
#     try:
#         data = obj.process_api(**{'block': int(block_height)})
#         proceed_slpdb_checking = True
#     except Exception as exc:
#         LOGGER.error(exc)
#         proceed_slpdb_checking = False

#     # Checking of transactions using SLPDB
#     if data['status'] == 'success' and proceed_slpdb_checking:
#         LOGGER.info(f'CHECKING BLOCK {block_height} via SLPDB')
#         redis_storage = settings.REDISKV
#         transactions = data['data']['c']
#         slpdb_total_transactions = len(transactions)
#         for transaction in transactions:
#             if transaction['tokenDetails']['valid']:
#                 if transaction['tokenDetails']['detail']['transactionType'].lower() == 'send':
#                     token_id = transaction['tokenDetails']['detail']['tokenIdHex']
#                     token, _ = Token.objects.get_or_create(tokenid=token_id)
#                     if transaction['tokenDetails']['detail']['outputs'][0]['address'] is not None:
#                         spent_index = 1
#                         for trans in transaction['tokenDetails']['detail']['outputs']:
#                             save_record.delay(
#                                 token.tokenid,
#                                 trans['address'],
#                                 transaction['txid'],
#                                 trans['amount'],
#                                 'SLPDB-block-scanner',
#                                 blockheightid=block_instance.id,
#                                 spent_index=spent_index
#                             )
#                             spent_index += 1

           
@shared_task(bind=True, queue='checktransaction', max_retries=20)
def checktransaction(self, txn_id):
    status = 'failed'
    url = f'https://rest.bitcoin.com/v2/transaction/details/{txn_id}'
    try:
        response = requests.get(url)
    except Exception as exc:
        self.retry(countdown=60)
    if response.status_code == 200:
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
                                        "per-bch-blockheight",
                                        blockheightid=blockheight_obj.id,
                                        spent_index=out['spentIndex']
                                    )
            LOGGER.info(f'CUSTOM CHECK FOR TRANSACTION {txn_id}')
            status = 'success'
    else:
        self.retry(countdown=60)
    return status
    
# @shared_task(bind=True, queue='slpbitcoinsocket', time_limit=600)
# def slpbitcoinsocket(self):
#     """
#     A live stream of SLP transactions via Bitcoin
#     """
#     url = "https://slpsocket.bitcoin.com/s/ewogICJ2IjogMywKICAicSI6IHsKICAgICJmaW5kIjoge30KICB9Cn0="
#     resp = requests.get(url, stream=True)
#     source = 'slpsocket.bitcoin.com'
#     msg = 'Service not available!'
#     LOGGER.info('socket ready in : %s' % source)
#     redis_storage = settings.REDISKV
#     if b'slpbitcoinsocket' not in redis_storage.keys():
#         redis_storage.set('slpbitcoinsocket', 0)
#     withsocket = int(redis_storage.get('slpbitcoinsocket'))
#     if not withsocket:
#         for content in resp.iter_content(chunk_size=1024*1024):
#             redis_storage.set('slpbitcoinsocket', 1)
#             decoded_text = content.decode('utf8')
#             if 'heartbeat' not in decoded_text:
#                 data = decoded_text.strip().split('data: ')[-1]
#                 proceed = True
#                 try:
#                     readable_dict = json.loads(data)
#                 except json.decoder.JSONDecodeError as exc:
#                     msg = f'Its alright. This is an expected error. --> {exc}'
#                     LOGGER.error(msg)
#                     proceed = False
#                 except Exception as exc:
#                     msg = f'This is novel issue {exc}'
#                     break
#                 if proceed:
#                     if len(readable_dict['data']) != 0:
#                         token_id = readable_dict['data'][0]['slp']['detail']['tokenIdHex']
#                         token_obj, _ =  Token.objects.get_or_create(tokenid=token_id)
#                         # if token_query.exists():
#                         if 'tx' in readable_dict['data'][0].keys():
#                             if readable_dict['data'][0]['slp']['valid']:
#                                 txn_id = readable_dict['data'][0]['tx']['h']
#                                 for trans in readable_dict['data'][0]['slp']['detail']['outputs']:
#                                     slp_address = trans['address']
#                                     amount = float(trans['amount'])
#                                     spent_index = trans['spentIndex']
#                                     args = (
#                                         token_obj.tokenid,
#                                         slp_address,
#                                         txn_id,
#                                         amount,
#                                         source,
#                                         None,
#                                         spent_index
#                                     )
#                                     save_record(*args)
#         LOGGER.error(msg)
#         redis_storage.set('slpbitcoinsocket', 0)
#     else:
#         LOGGER.info('slpbitcoin is still running')

# @shared_task(bind=True, queue='bitdbquery')
# def bitdbquery(self):
#     BITDB_URL = 'https://bitdb.fountainhead.cash/q/'
#     source = 'bitdbquery'
#     query = {
#         "v": 3,
#         "q": {
#             "find": {
#             },
#             "limit": 5000
#         }
#     }
#     json_string = bytes(json.dumps(query), 'utf-8')
#     url = base64.b64encode(json_string)
#     resp = requests.get(BITDB_URL + url.decode('utf-8'))
#     data = resp.json()
#     for row in data['u']:
#         txn_id = row['tx']['h']
#         counter = 1
#         for out in row['out']: 
#             args = tuple()
#             amount = out['e']['v'] / 100000000
#             spent_index = out['e']['i']
#             if 'a' in out['e'].keys():
#                 bchaddress = 'bitcoincash:' + str(out['e']['a'])
#                 args = (
#                     'bch',
#                     bchaddress,
#                     txn_id,
#                     amount,
#                     source,
#                     None,
#                     spent_index
#                 )
#                 # For intant recording of transaction, its better not to delay.
#                 save_record(*args)
#             counter += 1

# @shared_task(bind=True, queue='bitsocket', time_limit=600)
# def bitsocket(self):
#     """
#     A live stream of BCH transactions via bitsocket
#     """
#     url = "https://bitsocket.bch.sx/s/ewogICJ2IjogMywKICAicSI6IHsKICAgICJmaW5kIjoge30KICB9Cn0="
#     resp = requests.get(url, stream=True)
#     source = 'bitsocket'
#     msg = 'Service not available!'
#     LOGGER.info('socket ready in : %s' % source)
#     redis_storage = settings.REDISKV
#     previous = ''
#     if b'bitsocket' not in redis_storage.keys():
#         redis_storage.set('bitsocket', 0)
#     withsocket = int(redis_storage.get('bitsocket'))
#     if not withsocket:
#         for content in resp.iter_content(chunk_size=1024*1024):
#             redis_storage.set('bitsocket', 1)
#             loaded_data = None
#             try:
#                 content = content.decode('utf8')
#                 if '"tx":{"h":"' in previous:
#                     data = previous + content
#                     data = data.strip().split('data: ')[-1]
#                     loaded_data = json.loads(data)

#                     proceed = True
#             except (ValueError, UnicodeDecodeError, TypeError) as exc:
#                 msg = traceback.format_exc()
#                 msg = f'Its alright. This is an expected error. --> {msg}'
#                 # LOGGER.error(msg)
#             except json.decoder.JSONDecodeError as exc:
#                 msg = f'Its alright. This is an expected error. --> {exc}'
#                 # LOGGER.error(msg)
#             except Exception as exc:
#                 msg = f'Novel exception found --> {exc}'
#                 break
#             previous = content
#             if loaded_data is not None:
#                 if len(loaded_data['data']) != 0:
#                     txn_id = loaded_data['data'][0]['tx']['h']
#                     for out in loaded_data['data'][0]['out']: 
#                         amount = out['e']['v'] / 100000000
#                         spent_index = out['e']['i']
#                         if amount and 'a' in out['e'].keys():
#                             bchaddress = 'bitcoincash:' + str(out['e']['a'])
#                             args = (
#                                 'bch',
#                                 bchaddress,
#                                 txn_id,
#                                 amount,
#                                 source,
#                                 None,
#                                 spent_index
#                             )
#                             # For instant saving of transaction, its better not to delay task.
#                             save_record(*args)
#         LOGGER.error(msg)
#         redis_storage.set('bitsocket', 0)
#     else:
#         LOGGER.info('bitsocket is still running')

# @shared_task(bind=True, queue='bitcoincash_tracker')
# def bitcoincash_tracker(self,id):
#     blockheight_obj= BlockHeight.objects.get(id=id)
#     url = f"https://rest.bitcoin.com/v2/block/detailsByHeight/{blockheight_obj.number}"
#     resp = requests.get(url)
#     data = json.loads(resp.text)
#     if 'tx' in data.keys():
#         for txn_id in data['tx']:
#             trans = Transaction.objects.filter(txid=txn_id)
#             if not trans.exists():
#                 url = f'https://rest.bitcoin.com/v2/transaction/details/{txn_id}'
#                 response = requests.get(url)
#                 if response.status_code == 200:
#                     data = json.loads(response.text)
#                     if 'vout' in data.keys():
#                         for out in data['vout']:
#                             if 'scriptPubKey' in out.keys():
#                                 if 'cashAddrs' in out['scriptPubKey'].keys():
#                                     for cashaddr in out['scriptPubKey']['cashAddrs']:
#                                         if cashaddr.startswith('bitcoincash:'):
#                                             args = (
#                                                 'bch',
#                                                 cashaddr,
#                                                 txn_id,
#                                                 out['value'],
#                                                 "alt-bch-tracker",
#                                                 blockheight_obj.id,
#                                                 out['spentIndex']
#                                             )
#                                             # For instance saving of transaction, its better not to delay task
#                                             save_record(*args)

# @shared_task(bind=True, queue='bch_address_scanner')
# def bch_address_scanner(self, bchaddress=None):
#     addresses = [bchaddress]
#     if bchaddress is None:
#         addresses = BchAddress.objects.filter(scanned=False)
#         if not addresses.exists(): 
#             BchAddress.objects.update(scanned=True)
#             addresses = BchAddress.objects.filter(scanned=False)
#         addresses = list(addresses.values_list('address',flat=True)[0:10])

#     source = 'bch-address-scanner'
#     url = 'https://rest.bitcoin.com/v2/address/transactions'
#     data = { "addresses": addresses}
#     resp = requests.post(url, json=data)
#     data = json.loads(resp.text)
#     for row in data:
#         for tr in row['txs']:
#             blockheight, created = BlockHeight.objects.get_or_create(number=tr['blockheight'])
#             for out in tr['vout']:
#                 amount = out['value']
#                 spent_index = tr['vout'][0]['spentIndex'] or 0
#                 if 'addresses' in out['scriptPubKey'].keys():
#                     for legacy in out['scriptPubKey']['addresses']:
#                         address_url = 'https://rest.bitcoin.com/v2/address/details/%s' % legacy
#                         address_response = requests.get(address_url)
#                         address_data = json.loads(address_response.text)
#                         args = (
#                             'bch',
#                             address_data['cashAddress'],
#                             tr['txid'],
#                             out['value'],
#                             source,
#                             blockheight.id,
#                             spent_index
#                         )
#                         LOGGER.info(f"{source} | txid : {tr['txid']} | amount : {out['value']}")
#                         save_record.delay(*args)

#     BchAddress.objects.filter(address__in=addresses).update(scanned=True)
    
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

# @shared_task(queue='spicebot_subscription')
# def spicebot_subscription(tokenid, tokenname):
#     obj = SpicebotTokens()
#     obj.register(tokenid, tokename)
#     obj.subscribe()

def remove_subscription(token_address, token_id, subscriber_id, platform):
    token = Token.objects.get(id=token_id)
    platform = platform.lower()
    subscriber = None

    if platform == 'telegram':
        subscriber = Subscriber.objects.get(telegram_user_details__id=subscriber_id)
    elif platform == 'slack':
        subscriber = Subscriber.objects.get(slack_user_details__id=subscriber_id)
    
    if token and subscriber:
        if token_address.startswith('bitcoincash'):
            address_obj = BchAddress.objects.get(address=token_address)
            subscription = Subscription.objects.filter(
                bch=address_obj,
                token=token
            )
        else:
            address_obj = SlpAddress.objects.get(address=token_address)
            subscription = Subscription.objects.filter(
                slp=address_obj,
                token=token
            ) 
        
        if subscription.exists():
            subscription.delete()
            return True
    
    return False

def save_subscription(token_address, token_id, subscriber_id, platform):
    # note: subscriber_id: unique identifier of telegram/slack user
    token = Token.objects.get(id=token_id)
    platform = platform.lower()
    subscriber = None

    # check telegram & slack user fields in subscriber
    if platform == 'telegram':
        subscriber = Subscriber.objects.get(telegram_user_details__id=subscriber_id)
    elif platform == 'slack':
        subscriber = Subscriber.objects.get(slack_user_details__id=subscriber_id)

    if token and subscriber:
        destination_address = None

        if token_address.startswith('bitcoincash'):
            address_obj, created = BchAddress.objects.get_or_create(address=token_address)
            subscription_obj, created = Subscription.objects.get_or_create(
                bch=address_obj,
                token=token
            )
        else:
            address_obj, created = SlpAddress.objects.get_or_create(address=token_address)
            subscription_obj, created = Subscription.objects.get_or_create(
                slp=address_obj,
                token=token
            ) 

        if platform == 'telegram':
            destination_address = settings.TELEGRAM_DESTINATION_ADDR
        elif platform == 'slack':
            destination_address = settings.SLACK_DESTINATION_ADDR

        if created:
            sendTo, created = SendTo.objects.get_or_create(address=destination_address)

            subscription_obj.address.add(sendTo)
            subscription_obj.token = token
            subscription_obj.save()
            
            subscriber.subscription.add(subscription_obj)
            return True

    return False

def register_user(user_details, platform):
    platform = platform.lower()
    user_id = user_details['id']

    uname_pass = f"{platform}-{user_id}"

    new_user, created = User.objects.get_or_create(
        username=uname_pass,
        password=uname_pass
    )

    new_subscriber = Subscriber()
    new_subscriber.user = new_user
    new_subscriber.confirmed = True

    if platform == 'telegram':
        new_subscriber.telegram_user_details = user_details
    elif platform == 'slack':
        new_subscriber.slack_user_details = user_details
        
    new_subscriber.save()

# @shared_task(queue='updates')
# def updates():
#     start = timezone.now()- datetime.timedelta(days=7)
#     ending = timezone.now() - datetime.timedelta(seconds=4800)
#     qs = BlockHeight.objects.filter(
#         Q(created_datetime__gte=start) & Q(created_datetime__lte=ending)
#     )
#     to_process_blocks = qs.filter(processed=False)
#     for block in to_process_blocks:
#         first_blockheight_scanner.delay(block.id)
#     LOGGER.info('Updated blocks!')