"""
Dedicated to all celery tasks for SLPNotify Only
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
from main.utils import slpdb, missing_blocks, block_setter
from django.conf import settings
import traceback, datetime
from sseclient import SSEClient
LOGGER = logging.getLogger(__name__)
from django.db import transaction as trans
from django.core.exceptions import ObjectDoesNotExist
import base64
import sseclient

@shared_task(bind=True, queue='client_acknowledgement', max_retries=3)
def client_acknowledgement(self, token, transactionid):
    try:
        token_obj = Token.objects.get(tokenid=token)
    except ObjectDoesNotExist:
        token_obj = Token.objects.get(name=token)
    # subscriptions = Subscription.objects.filter(token=token_obj).values('address__address').distinct()
    
    trans = Transaction.objects.get(id=transactionid)
    block = None
    if trans.blockheight:
        block = trans.blockheight.number
    retry = False
    # address can be bch or slp
    address = trans.address
    if 'bitcoincash' in address:
        subscription = Subscription.objects.filter(bch__address=address)
    else:
        subscription = Subscription.objects.filter(slp__address=address)
    if subscription.exists():
        trans.subscribed = True
        subscription = subscription.first()
        target_addresses = subscription.address.all()

        if target_addresses.count() == 0:
            sendto_obj = SendTo.objects.first()
            subscription.address.add(sendto_obj)
            target_addresses = [sendto_obj]
            
        for target_address in target_addresses:
            #check if telegram/slack user
            data = {
                'amount': trans.amount,
                'address': trans.address,
                'source': trans.source,
                'token': token_obj.tokenid,
                'txid': trans.txid,
                'block': block,
                'spent_index':trans.spentIndex
            }

            # retrieve subscribers' channel_id to be added to payload as a list (for Slack)
            
            if target_address.address == settings.SLACK_DESTINATION_ADDR:
                subscribers = subscription.subscriber.exclude(slack_user_details={})
                botlist = list(subscribers.values_list('slack_user_details__channel_id', flat=True))
                data['channel_id_list'] = json.dumps(botlist)
                
            if target_address.address == settings.TELEGRAM_DESTINATION_ADDR:
                subscribers = subscription.subscriber.exclude(telegram_user_details={})
                botlist = list(subscribers.values_list('telegram_user_details__id', flat=True))
                data['chat_id_list'] = json.dumps(botlist)
             

            resp = requests.post(target_address.address,data=data)
            if resp.status_code == 200:
                response_data = json.loads(resp.text)
                if response_data['success']:
                    trans.acknowledge = True
                    trans.queued = False
            elif resp.status_code == 404:
                LOGGER.error(f'this is no longer valid > {target_address}')
            else:
                retry = True
                trans.acknowledge = False
        # This is no longer reliable since a subscriber can have multiple subscription
        trans.save()
    if retry:
        self.retry(countdown=180)
    else:
        return 'success'

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
    # with_existing_trans = Transaction.objects.filter(txid=transactionid).first()
    # if with_existing_trans:
    #     if with_existing_trans.source != source:
    #         return f"Transaction {with_existing_trans.txid} was already processed by {with_existing_trans.source}."

    try:
        spent_index = int(spent_index)
    except TypeError as exc:
        spent_index = 0

    with trans.atomic():
        try:
            token_obj = Token.objects.get(tokenid=token)
        except ObjectDoesNotExist:
            token_obj = Token.objects.get(name=token)
        
        transaction_obj, transaction_created = Transaction.objects.get_or_create(
            txid=transactionid,
            address=transaction_address,
            token=token_obj,
            amount=amount,
            spentIndex=spent_index
        )
        
        if not transaction_obj.source:
            transaction_obj.source = source
        if blockheightid is not None:
            transaction_obj.blockheight_id = blockheightid
        transaction_obj.save()
        if token == 'bch':
            address_obj, created = BchAddress.objects.get_or_create(address=transaction_address)
        else:
            address_obj, created = SlpAddress.objects.get_or_create(address=transaction_address)
        address_obj.transactions.add(transaction_obj)
        address_obj.save()
        client_acknowledgement.delay(token, transaction_obj.id)

@shared_task(queue='suspendtoredis')
def suspendtoredis(txn_id, blockheightid, currentcount, total_transactions):
    redis_storage = settings.REDISKV
    if b'deposit_filter' not in redis_storage.keys():
        data = json.dumps([])
        redis_storage.set('deposit_filter', data)
    data = json.loads(redis_storage.get('deposit_filter'))
    data.append({
        'txn_id': txn_id,
        'blockheightid': blockheightid,
        'currentcount': currentcount,
        'total_transactions': total_transactions
    })
    suspended_data = json.dumps(data)
    redis_storage.set('deposit_filter', suspended_data)
    return f'{txn_id} - Suspended for a 30 minutes due to request limits on rest.bitcoin.com'

@shared_task(queue='deposit_filter')
def deposit_filter(txn_id, blockheightid, currentcount, total_transactions):
    obj = BlockHeight.objects.get(id=blockheightid)
    LOGGER.info(f"BLOCK {obj.number} | {currentcount} out of {total_transactions}")
    """
    Tracks every transactions that belongs to the registered token and blockheight.
    """
    # If txn_id is already in db, we'll just update its blockheight 
    # To minimize send request on rest.bitcoin.com
    qs = Transaction.objects.filter(txid=txn_id)
    if qs.exists():
        instance = qs.first()
        if not instance.amount or not instance.source:
            return 'success'
    status = 'failed'
    transaction_url = 'https://rest.bitcoin.com/v2/slp/txDetails/%s' % (txn_id)
    proceed = True
    try:
        transaction_response = requests.get(transaction_url)
    except Exception as exc:
        proceed = False
    if proceed == True:
        if transaction_response.status_code == 200:
            try:
                transaction_data = json.loads(transaction_response.text)
            except Exception as exc:
                transaction_data = {}
            if 'tokenInfo' in transaction_data.keys():
                if transaction_data['tokenInfo']:
                    if 'tokenIsValid' in transaction_data['tokenInfo'].keys():
                        if transaction_data['tokenInfo']['tokenIsValid']:
                            if transaction_data['tokenInfo']['transactionType'].lower() == 'send':
                                transaction_token_id = transaction_data['tokenInfo']['tokenIdHex']
                                token_query = Token.objects.filter(tokenid=transaction_token_id)
                                if token_query.exists():
                                    
                                    send_outputs = transaction_data['tokenInfo']['sendOutputs']

                                    # the last index is intended to sender's current balance so we'll going to remove it in send_ouputs.
                                    send_outputs.pop(-1)


                                    spent_index = 1
                                    
                                    for output in send_outputs:
                                        amount = float(output)
                                                                        
                                        for legacy in transaction_data['retData']['vout'][spent_index]['scriptPubKey']['addresses']:
                                            """ 
                                                Since there's no specification for slp addresses, we'll use legacy address that was 
                                                mapped in every send ouputs.
                                            """
                                            
                                            try:
                                                address_url = 'https://rest.bitcoin.com/v2/address/details/%s' % legacy
                                                address_response = requests.get(address_url)
                                                address_data = json.loads(address_response.text)
                                            except Exception as exc:
                                                # Once fail in sending request, we'll store given params to
                                                # redis temporarily and retry after 30 minutes cooldown.
                                                msg = f'---> FOUND this error {exc} --> Now Delaying...'
                                                LOGGER.error(msg)
                                                proceed = False

                                            if (not 'error' in address_data.keys()) and proceed == True:
                                                token_obj = token_query.first()
                                                args = (
                                                    token_obj.tokenid,
                                                    address_data['slpAddress'],
                                                    txn_id,
                                                    amount,
                                                    "per-blockheight",
                                                    blockheightid,
                                                    spent_index
                                                )
                                                save_record.delay(*args)
                                                print(args)
                                                status = 'success'

                                        spent_index += 1
                    else:
                        LOGGER.error(f'Transaction {txn_id} was invalidated at rest.bitcoin.com')
                else:
                    # Transaction with no token is a BCH transaction and have to be scanned.
                    status = 'success'
                    checktransaction.delay(txn_id)


        elif transaction_response.status_code == 404:
            status = 'success'
                        
    if currentcount == total_transactions:
        obj = BlockHeight.objects.get(id=blockheightid)
        obj.processed=True
        obj.save()
    if status == 'failed':
        pass
        # Once error found, we'll saved its params to
        # redis temporarily and resume it after 2 minutes cooldown.
        msg = f'!!! Error found !!! Suspending to redis...'
        LOGGER.error(msg)
        suspendtoredis.delay(txn_id, blockheightid, currentcount, total_transactions)
    if status == 'success':
        Transaction.objects.filter(txid=txn_id).update(scanning=False)
        BlockHeight.objects.filter(id=blockheightid).update(currentcount=currentcount)
    return f" {status} : {txn_id}"

@shared_task(queue='openfromredis')
def openfromredis():
    redis_storage = settings.REDISKV
    if b'deposit_filter' not in redis_storage.keys():
        data = json.dumps([])
        redis_storage.set('deposit_filter', data)
    deposit_filter = redis_storage.get('deposit_filter')
    transactions = json.loads(deposit_filter)
    if len(transactions) is not 0:
        for params in transactions:
            LOGGER.info(f"rescanning txn_id - {params['txn_id']}")
            deposit_filter(
                params['txn_id'],
                params['blockheightid'],
                params['currentcount'],
                params['total_transactions']
            )
    
@shared_task(queue='slpdb_token_scanner')
def slpdb_token_scanner():
    tokens = Token.objects.all()
    for token in tokens:
        obj = slpdb.SLPDB()
        data = obj.process_api(**{'tokenid': token.tokenid})
        if data['status'] == 'success':
            for transaction in data['data']['c']:
                if transaction['tokenDetails']['valid']:
                    required_keys = transaction.keys()
                    tx_exists = 'txid' in required_keys
                    token_exists = 'tokenDetails' in required_keys
                    blk_exists = 'blk' in required_keys
                    if  tx_exists and token_exists and blk_exists:
                        tokenid = transaction['tokenDetails']['detail']['tokenIdHex']
                        tokenqs = Token.objects.filter(tokenid=tokenid)
                        if tokenqs.exists():
                            # Block 625228 is the beginning...
                            # if transaction['blk'] >= 625228:
                            if transaction['blk'] >= 625190:    
                                token_obj = tokenqs.first()
                                block, created = BlockHeight.objects.get_or_create(number=transaction['blk'])
                                if created:
                                    first_blockheight_scanner.delay(block.id)
                                transaction['tokenDetails']['detail']['outputs'].pop(-1)
                                spent_index = 1
                                for trans in transaction['tokenDetails']['detail']['outputs']:
                                    amount = trans['amount']
                                    slpaddress = trans['address']
                                    args = (
                                        token_obj.tokenid,
                                        slpaddress,
                                        transaction['txid'],
                                        amount,
                                        "slpdb_token_scanner",
                                        block.id,
                                        spent_index
                                    )
                                    save_record.delay(*args)
                                    print(args)
                                    spent_index += 1


@shared_task(queue='latest_blockheight_getter')
def latest_blockheight_getter():    
    """
    Intended for checking new blockheight.
    This will beat every 5 seconds.
    """
    proceed = False
    url = 'https://rest.bitcoin.com/v2/blockchain/getBlockchainInfo'
    try:
        resp = requests.get(url)
        number = json.loads(resp.text)['blocks']
        obj, created = BlockHeight.objects.get_or_create(number=number)
        if created:
            LOGGER.info(f'===== NEW BLOCK {number} =====')
            block_setter(number, new=True)
            bitcoincash_tracker.delay(obj.id)
        else:
            # IF THERE'S ANY missed/unprocessed blocks, this task will automatically scan atleast 1 recent block.
            blocks = list(BlockHeight.objects.all().order_by('number').values_list('number',flat=True))
            blocks = list(missing_blocks(blocks,0,len(blocks)-1))
            event = 'MISSED'
            if not len(blocks):
                blocks = list(BlockHeight.objects.filter(processed=False).order_by('-number').values_list('number', flat=True))
                event = 'UNPROCESSED'
            if len(blocks):
                number = blocks[-1]
                added = block_setter(number, new=False)
                if added:
                    obj, created = BlockHeight.objects.get_or_create(number=number)
                    bitcoincash_tracker.delay(obj.id)   
                    LOGGER.info(f'===== SCANNING {event} BLOCK {number} =====')
    except Exception as exc:
        LOGGER.error(exc)

@shared_task(bind=True, queue='second_blockheight_scanner')
def second_blockheight_scanner(self):
    redis_storage = settings.REDISKV
    blocks = redis_storage.keys("BLOCK-*")
    if blocks:
        blocks.sort()
        key = str(blocks[0].decode())
        number = int(key.split('-')[-1])
        blockheight_instance = BlockHeight.objects.get(number=number)
        transactions = json.loads(redis_storage.get(key))
        total_transactions = len(transactions)
        counter = 1
        blockheight_instance.transactions_count = total_transactions
        blockheight_instance.save()
        redis_storage.delete(key) 
        for txn_id in transactions:
            for token in Token.objects.all():
                deposit_filter.delay(
                    txn_id,
                    blockheight_instance.id,
                    counter,
                    total_transactions
                )
            counter += 1
        LOGGER.info(f"  =======  PROCESSED BLOCK {number}   =======  ")
    else:
        LOGGER.info(f"  =======  NO BLOCKS FOUND   =======  ")
        
@shared_task(bind=True, queue='first_blockheight_scanner', max_retries=10)
def first_blockheight_scanner(self, id=None):
    if id is None:
        redis_storage = settings.REDISKV
        blocks = json.loads(redis_storage.get('PENDING-BLOCKS'))
        if len(blocks) == 0:
            return 'success'
        number = blocks[0]
        blockheight_instance = BlockHeight.objects.get(number=number)
        blocks.remove(number)
        data = json.dumps(blocks)
        redis_storage.set('PENDING-BLOCKS', data)
    else:
        blockheight_instance = BlockHeight.objects.get(id=id)
    """
    Process missed transactions per blockheight
    """
    heightnumber = blockheight_instance.number
    blockheight_instance.processed = False
    blockheight_instance.save()
    obj = slpdb.SLPDB()
    try:
        data = obj.process_api(**{'block': int(heightnumber)})
        proceed_slpdb_checking = True
    except Exception as exc:
        LOGGER.error(exc)
        proceed_slpdb_checking = False
    if data['status'] == 'success' and proceed_slpdb_checking:
        LOGGER.info(f'CHECKING BLOCK {heightnumber} via SLPDB')
        redis_storage = settings.REDISKV
        transactions = data['data']['c']
        slpdb_total_transactions = len(transactions)
        for transaction in transactions:
            if transaction['tokenDetails']['valid']:
                if transaction['tokenDetails']['detail']['transactionType'].lower() == 'send':
                    token = transaction['tokenDetails']['detail']['tokenIdHex']
                    qs = Token.objects.filter(tokenid=token)
                    if qs.exists():
                        if transaction['tokenDetails']['detail']['outputs'][0]['address'] is not None:
                            spent_index = 1
                            for trans in transaction['tokenDetails']['detail']['outputs']:
                                save_record(
                                    transaction['tokenDetails']['detail']['tokenIdHex'],
                                    trans['address'],
                                    transaction['txid'],
                                    trans['amount'],
                                    'SLPDB-block-scanner',
                                    blockheightid=blockheight_instance.id,
                                    spent_index=spent_index
                                )
                                spent_index += 1
    LOGGER.info(f'CHECKING BLOCK {heightnumber} via REST.BITCOIN.COM')
    url = 'https://rest.bitcoin.com/v2/block/detailsByHeight/%s' % heightnumber
    resp = requests.get(url)
    if resp.status_code == 200:
        data = json.loads(resp.text)
        if 'error' not in data.keys():
            # Save all transactions to redis after 60 minutes to avoid request timeouts.
            transactions = json.dumps(data['tx'])
            key = f"BLOCK-{heightnumber}"
            redis_storage.set(key, transactions)
        else:
            self.retry(countdown=120)
    else:
        self.retry(countdown=120)
            
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
                                    save_record(
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
    
@shared_task(bind=True, queue='slpbitcoinsocket')
def slpbitcoinsocket(self):
    """
    A live stream of SLP transactions via Bitcoin
    """
    url = "https://slpsocket.bitcoin.com/s/ewogICJ2IjogMywKICAicSI6IHsKICAgICJmaW5kIjoge30KICB9Cn0="
    resp = requests.get(url, stream=True)
    source = 'slpsocket.bitcoin.com'
    msg = 'Service not available!'
    LOGGER.info('socket ready in : %s' % source)
    redis_storage = settings.REDISKV
    if b'slpbitcoinsocket' not in redis_storage.keys():
        redis_storage.set('slpbitcoinsocket', 0)
    withsocket = int(redis_storage.get('slpbitcoinsocket'))
    if not withsocket:
        for content in resp.iter_content(chunk_size=1024*1024):
            redis_storage.set('slpbitcoinsocket', 1)
            decoded_text = content.decode('utf8')
            if 'heartbeat' not in decoded_text:
                data = decoded_text.strip().split('data: ')[-1]
                proceed = True
                try:
                    readable_dict = json.loads(data)
                except json.decoder.JSONDecodeError as exc:
                    msg = f'Its alright. This is an expected error. --> {exc}'
                    LOGGER.error(msg)
                    proceed = False
                except Exception as exc:
                    msg = f'This is novel issue {exc}'
                    break
                if proceed:
                    if len(readable_dict['data']) != 0:
                        token_query =  Token.objects.filter(tokenid=readable_dict['data'][0]['slp']['detail']['tokenIdHex'])
                        if token_query.exists():
                            if 'tx' in readable_dict['data'][0].keys():
                                if readable_dict['data'][0]['slp']['valid']:
                                    txn_id = readable_dict['data'][0]['tx']['h']
                                    for trans in readable_dict['data'][0]['slp']['detail']['outputs']:
                                        slp_address = trans['address']
                                        amount = float(trans['amount'])
                                        spent_index = trans['spentIndex']
                                        token_obj = token_query.first()
                                        args = (
                                            token_obj.tokenid,
                                            slp_address,
                                            txn_id,
                                            amount,
                                            source,
                                            None,
                                            spent_index
                                        )
                                        save_record.delay(*args)
                                        print(args)
        LOGGER.error(msg)
        redis_storage.set('slpbitcoinsocket', 0)
    else:
        LOGGER.info('slpbitcoin is still running')

@shared_task(bind=True, queue='slpfountainheadsocket')
def slpfountainheadsocket(self):
    """
    A live stream of SLP transactions via FountainHead
    """
    url = "https://slpsocket.fountainhead.cash/s/ewogICJ2IjogMywKICAicSI6IHsKICAgICJmaW5kIjogewogICAgfQogIH0KfQ=="
    resp = requests.get(url, stream=True)
    source = 'slpsocket.fountainhead.cash'
    LOGGER.info('socket ready in : %s' % source)
    previous = ''
    msg = 'Service not available!'
    redis_storage = settings.REDISKV
    if b'slpfountainheadsocket' not in redis_storage.keys():
        redis_storage.set('slpfountainheadsocket', 0)
    withsocket = int(redis_storage.get('slpfountainheadsocket'))
    if not withsocket:
        for content in resp.iter_content(chunk_size=1024*1024):
            loaded_data = None
            redis_storage.set('slpfountainheadsocket', 1)
            try:
                content = content.decode('utf8')
                if '"tx":{"h":"' in previous:
                    data = previous + content
                    data = data.strip().split('data: ')[-1]
                    loaded_data = json.loads(data)
            except (ValueError, UnicodeDecodeError, TypeError) as exc:
                msg = traceback.format_exc()
                msg = f'Its alright. This is an expected error. --> {msg}'
                LOGGER.error(msg)
            except json.decoder.JSONDecodeError as exc:
                msg = f'Its alright. This is an expected error. --> {exc}'
                LOGGER.error(msg)
            except Exception as exc:
                msg = f'Novel exception found --> {exc}'
                break
            previous = content
            if loaded_data is not None:
                if len(loaded_data['data']) > 0:
                    info = loaded_data['data'][0]
                    if 'slp' in info.keys():
                        if info['slp']['valid']:
                            if 'detail' in info['slp'].keys():
                                if 'tokenIdHex' in info['slp']['detail'].keys():
                                    token_query =  Token.objects.filter(tokenid=info['slp']['detail']['tokenIdHex'])
                                    if token_query.exists():
                                        spent_index = 1
                                        for trans in info['slp']['detail']['outputs']:
                                            amount = float(trans['amount'])
                                            slp_address = trans['address']
                                            if 'tx' in info.keys():
                                                txn_id = info['tx']['h']
                                                token_obj = token_query.first()
                                                args = (
                                                    info['slp']['detail']['tokenIdHex'],
                                                    slp_address,
                                                    txn_id,
                                                    amount,
                                                    source,
                                                    None,
                                                    spent_index
                                                )
                                                save_record.delay(*args)
                                                print(args)
                                            spent_index += 1
        LOGGER.error(msg)
        redis_storage.set('slpfountainheadsocket', 0)
    else:
        LOGGER.info('slpfountainhead is still running')

        
@shared_task(bind=True, queue='slpstreamfountainheadsocket')
def slpstreamfountainheadsocket(self):
    """
    A live stream of SLP transactions via SLP Stream Fountainhead
    """
    url = "https://slpstream.fountainhead.cash/s/ewogICJ2IjogMywKICAicSI6IHsKICAgICJmaW5kIjoge30KICB9Cn0="
    resp = requests.get(url, stream=True)
    source = 'slpstreamfountainhead'
    msg = 'Service not available!'
    LOGGER.info('socket ready in : %s' % source)
    redis_storage = settings.REDISKV
    if b'slpstreamfountainheadsocket' not in redis_storage.keys():
        redis_storage.set('slpstreamfountainheadsocket', 0)
    withsocket = int(redis_storage.get('slpstreamfountainheadsocket'))
    if not withsocket:
        for content in resp.iter_content(chunk_size=1024*1024):
            redis_storage.set('slpstreamfountainheadsocket', 1)
            decoded_text = content.decode('utf8')
            if 'heartbeat' not in decoded_text:
                data = decoded_text.strip().split('data: ')[-1]
                proceed = True
                try:
                    readable_dict = json.loads(data)
                except json.decoder.JSONDecodeError as exc:
                    msg = f'Its alright. This is an expected error. --> {exc}'
                    LOGGER.error(msg)
                    proceed = False
                except Exception as exc:
                    msg = f'This is a novel issue {exc}'
                    LOGGER.error(msg)
                    break
                if proceed:
                    if len(readable_dict['data']) != 0:
                        token_query =  Token.objects.filter(tokenid=readable_dict['data'][0]['slp']['detail']['tokenIdHex'])
                        if token_query.exists():
                            if 'tx' in readable_dict['data'][0].keys():
                                if readable_dict['data'][0]['slp']['valid']:
                                    txn_id = readable_dict['data'][0]['tx']['h']
                                    for trans in readable_dict['data'][0]['slp']['detail']['outputs']:
                                        slp_address = trans['address']
                                        amount = float(trans['amount']) / 100000000
                                        spent_index = trans['spentIndex']
                                        token_obj = token_query.first()
                                        tr_qs = Transaction.objects.filter(address=slp_address, txid=txn_id)
                                        args = (
                                            token_obj.tokenid,
                                            slp_address,
                                            txn_id,
                                            amount,
                                            source,
                                            None,
                                            spent_index
                                        )
                                        save_record.delay(*args)
                                        print(args)
        LOGGER.error(msg)
        redis_storage.set('slpstreamfountainheadsocket', 0)
    else:
        LOGGER.info('slpstreamfountainheadsocket is still running')

@shared_task(bind=True, queue='bitdbquery')
def bitdbquery(self):
    BITDB_URL = 'https://bitdb.fountainhead.cash/q/'
    source = 'bitdbquery'
    query = {
        "v": 3,
        "q": {
            "find": {
            },
            "limit": 30000
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
                save_record.delay(*args)
            print(f"{counter} | {args}")
            counter += 1


@shared_task(bind=True, queue='bitsocket')
def bitsocket(self):

    """
    A live stream of BCH transactions via bitsocket
    """
    url = "https://bitsocket.bch.sx/s/ewogICJ2IjogMywKICAicSI6IHsKICAgICJmaW5kIjoge30KICB9Cn0="
    resp = requests.get(url, stream=True)
    source = 'bitsocket'
    msg = 'Service not available!'
    LOGGER.info('socket ready in : %s' % source)
    redis_storage = settings.REDISKV
    previous = ''
    if b'bitsocket' not in redis_storage.keys():
        redis_storage.set('bitsocket', 0)
    withsocket = int(redis_storage.get('bitsocket'))
    if not withsocket:
        for content in resp.iter_content(chunk_size=1024*1024):
            redis_storage.set('bitsocket', 1)
            loaded_data = None
            try:
                content = content.decode('utf8')
                if '"tx":{"h":"' in previous:
                    data = previous + content
                    data = data.strip().split('data: ')[-1]
                    loaded_data = json.loads(data)

                    proceed = True
            except (ValueError, UnicodeDecodeError, TypeError) as exc:
                msg = traceback.format_exc()
                msg = f'Its alright. This is an expected error. --> {msg}'
                # LOGGER.error(msg)
            except json.decoder.JSONDecodeError as exc:
                msg = f'Its alright. This is an expected error. --> {exc}'
                # LOGGER.error(msg)
            except Exception as exc:
                msg = f'Novel exception found --> {exc}'
                break
            previous = content
            if loaded_data is not None:
                if len(loaded_data['data']) != 0:
                    txn_id = loaded_data['data'][0]['tx']['h']
                    for out in loaded_data['data'][0]['out']: 
                        amount = out['e']['v'] / 100000000
                        spent_index = out['e']['i']
                        if amount and 'a' in out['e'].keys():
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
                            save_record.delay(*args)
                            print(args)
        LOGGER.error(msg)
        redis_storage.set('bitsocket', 0)
    else:
        LOGGER.info('bitsocket is still running')

@shared_task(bind=True, queue='bitcoincash_tracker')
def bitcoincash_tracker(self,id):
    blockheight_obj= BlockHeight.objects.get(id=id)
    url = f"https://rest.bitcoin.com/v2/block/detailsByHeight/{blockheight_obj.number}"
    resp = requests.get(url)
    data = json.loads(resp.text)
    if 'tx' in data.keys():
        for txn_id in data['tx']:
            trans = Transaction.objects.filter(txid=txn_id)
            if not trans.exists():
                url = f'https://rest.bitcoin.com/v2/transaction/details/{txn_id}'
                response = requests.get(url)
                if response.status_code == 200:
                    data = json.loads(response.text)
                    if 'vout' in data.keys():
                        for out in data['vout']:
                            if 'scriptPubKey' in out.keys():
                                if 'cashAddrs' in out['scriptPubKey'].keys():
                                    for cashaddr in out['scriptPubKey']['cashAddrs']:
                                        if cashaddr.startswith('bitcoincash:'):
                                            args = (
                                                'bch',
                                                cashaddr,
                                                txn_id,
                                                out['value'],
                                                "alt-bch-tracker",
                                                blockheight_obj.id,
                                                out['spentIndex']
                                            )
                                            save_record.delay(*args)
                                            print(args)

@shared_task(bind=True, queue='bch_address_scanner')
def bch_address_scanner(self, bchaddress=None):
    addresses = [bchaddress]
    if bchaddress is None:
        addresses = BchAddress.objects.filter(scanned=False)
        if not addresses.exists(): 
            BchAddress.objects.update(scanned=True)
            addresses = BchAddress.objects.filter(scanned=False)
        addresses = list(addresses.values_list('address',flat=True)[0:10])

    source = 'bch-address-scanner'
    url = 'https://rest.bitcoin.com/v2/address/transactions'
    data = { "addresses": addresses}
    resp = requests.post(url, json=data)
    data = json.loads(resp.text)
    for row in data:
        for tr in row['txs']:
            blockheight, created = BlockHeight.objects.get_or_create(number=tr['blockheight'])
            for out in tr['vout']:
                amount = out['value']
                spent_index = tr['vout'][0]['spentIndex'] or 0
                if 'addresses' in out['scriptPubKey'].keys():
                    for legacy in out['scriptPubKey']['addresses']:
                        address_url = 'https://rest.bitcoin.com/v2/address/details/%s' % legacy
                        address_response = requests.get(address_url)
                        address_data = json.loads(address_response.text)
                        args = (
                            'bch',
                            address_data['cashAddress'],
                            tr['txid'],
                            out['value'],
                            source,
                            blockheight.id,
                            spent_index
                        )
                        LOGGER.info(f"{source} | txid : {tr['txid']} | amount : {out['value']}")
                        save_record.delay(*args)
                        print(args)
    BchAddress.objects.filter(address__in=addresses).update(scanned=True)
    

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
