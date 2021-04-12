import math, logging, json, time, requests
from celery import shared_task
from main.models import (
    BlockHeight, 
    Token, 
    Transaction,
    SlpAddress, 
    Subscription, 
    BchAddress,
    Recipient
)
from celery.exceptions import MaxRetriesExceededError 
from main.utils import check_wallet_address_subscription
from main.utils import slpdb as slpdb_scanner
from main.utils import bitdb as bitdb_scanner
from django.conf import settings
from django.db import transaction as trans
from celery import Celery
from main.utils.chunk import chunks


LOGGER = logging.getLogger(__name__)
REDIS_STORAGE = settings.REDISKV

app = Celery('configs')



# NOTIFICATIONS
@shared_task(rate_limit='20/s', queue='send_telegram_message')
def send_telegram_message(message, chat_id):
    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    url = 'https://api.telegram.org/bot'
    response = requests.post(
        f"{url}{settings.TELEGRAM_BOT_TOKEN}/sendMessage", data=data
    )
    return f"send notification to {chat_id}"
    
@shared_task(bind=True, queue='client_acknowledgement', max_retries=3)
def client_acknowledgement(self, txid):
    this_transaction = Transaction.objects.filter(id=txid)
    third_parties = []
    if this_transaction.exists():
        transaction = this_transaction.first()
        block = None
        if transaction.blockheight:
            block = transaction.blockheight.number
        
        address = transaction.address 
        subscriptions = check_wallet_address_subscription(address)

        if subscriptions.exists():
            
            for subscription in subscriptions:

                recipient = subscription.recipient
                

                data = {
                    'amount': transaction.amount,
                    'address': transaction.address,
                    'source': 'WatchTower',
                    'token': transaction.token.tokenid,
                    'txid': transaction.txid,
                    'block': block,
                    'index': transaction.index
                }
                
                if recipient.valid:
                    if recipient.web_url:
                        resp = requests.post(recipient.web_url,data=data)
                        if resp.status_code == 200:
                            this_transaction.update(acknowledged=True)
                            LOGGER.info(f'ACKNOWLEDGEMENT SENT TX INFO : {transaction.txid} TO: {recipient.web_url}')
                        elif resp.status_code == 404 or resp.status_code == 522 or resp.status_code == 502:
                            Recipient.objects.filter(id=recipient.id).update(valid=False)
                            LOGGER.info(f"!!! ATTENTION !!! THIS IS AN INVALID DESTINATION URL: {recipient.web_url}")
                        else:
                            LOGGER.error(resp)
                            self.retry(countdown=3)

                    if recipient.telegram_id:

                        if transaction.token.name != 'bch':
                            message=f"""<b>WatchTower Notification</b> ℹ️
                                \n Address: {transaction.address}
                                \n Token: {transaction.token.name}
                                \n Token ID: {transaction.token.tokenid}
                                \n Amount: {transaction.amount}
                                \nhttps://explorer.bitcoin.com/bch/tx/{transaction.txid}
                            """
                        else:
                            message=f"""<b>WatchTower Notification</b> ℹ️
                                \n Address: {transaction.address}
                                \n Amount: {transaction.amount} BCH
                                \nhttps://explorer.bitcoin.com/bch/tx/{transaction.txid}
                            """

                        args = ('telegram' , message, recipient.telegram_id)
                        third_parties.append(args)
                        this_transaction.update(acknowledged=True)
    return third_parties


@shared_task(queue='save_record')   
def save_record(token, transaction_address, transactionid, amount, source, blockheightid=None, index=0):
    """
        token                : can be tokenid (slp token) or token name (bch)
        transaction_address  : the destination address where token had been deposited.
        transactionid        : transaction id generated over blockchain.
        amount               : the amount being transacted.
        source               : the layer that summoned this function (e.g SLPDB, Bitsocket, BitDB, SLPFountainhead etc.)
        blockheight          : an optional argument indicating the block height number of a transaction.
        index          : used to make sure that each record is unique based on slp/bch address in a given transaction_id
    """
    subscription = check_wallet_address_subscription(transaction_address)
    if not subscription.exists(): return None, None

    
    
    try:
        index = int(index)
    except TypeError as exc:
        index = 0
    

    with trans.atomic():
        
        transaction_created = False

        if token.lower() == 'bch':
            token_obj, _ = Token.objects.get_or_create(name=token)
        else:
            token_obj, _ = Token.objects.get_or_create(tokenid=token)
        

        #  USE FILTER AND BULK CREATE AS A REPLACEMENT FOR GET_OR_CREATE        
        tr = Transaction.objects.filter(
            txid=transactionid,
            address=transaction_address,
            token=token_obj,
            amount=amount,
            index=index,
        )
        
        if not tr.exists():

            transaction_data = {
                'txid':transactionid,
                'address':transaction_address,
                'token':token_obj,
                'amount':amount,
                'index':index,
                'source':source
            }
            transaction_list = [Transaction(**transaction_data)]
            Transaction.objects.bulk_create(transaction_list)
            transaction_created = True

        
        transaction_obj = Transaction.objects.get(
            txid=transactionid,
            address=transaction_address,
            token=token_obj,
            amount=amount,
            index=index
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

        
        return transaction_obj.id, transaction_created


@shared_task(bind=True, queue='input_scanner')
def input_scanner(self, txid, index, block_id=None):
    tr = Transaction.objects.filter(
        txid=txid,
        index=index
    )
    if tr.exists():
        if block_id:
            tr.update(
                spent=True,
                spend_block_height_id=block_id
            )
        else:
            tr.update(spent=True)

@shared_task(bind=True, queue='bitdbquery_transactions')
def bitdbquery_transaction(self, transaction, total, block_number, block_id):
    
    tx_count = int(REDIS_STORAGE.incr('BITDBQUERY_COUNT'))

    source = 'bitdb-query'
    
    txn_id = transaction['tx']['h']
    
    for out in transaction['out']: 
        args = tuple()
        amount = out['e']['v'] / 100000000
        index = out['e']['i']
        if 'a' in out['e'].keys():
            bchaddress = 'bitcoincash:' + str(out['e']['a'])

            subscription = check_wallet_address_subscription(bchaddress)
            LOGGER.info(f' * SOURCE: {source.upper()} | BLOCK {block_number} | TX: {txn_id} | BCH: {bchaddress} | {tx_count} OUT OF {total}')

            # Disregard bch address that are not subscribed.
            if subscription.exists():
                args = (
                    'bch',
                    bchaddress,
                    txn_id,
                    amount,
                    source,
                    block_id,
                    index
                )
                obj_id, created = save_record(*args)
                if created:
                    third_parties = client_acknowledgement(obj_id)
                    for platform in third_parties:
                        if 'telegram' in platform:
                            message = platform[1]
                            chat_id = platform[2]
                            send_telegram_message(message, chat_id)
           
    

    for _in in transaction['in']:
        txid = _in['e']['h']
        index= _in['e']['i']
        input_scanner(txid, index, block_id=block_id)

    
    
@shared_task(bind=True, queue='bitdbquery', max_retries=30)
def bitdbquery(self, block_id):
    try:
        block = BlockHeight.objects.get(id=block_id)
        if block.processed: return  # Terminate here if processed already
        divider = "\n\n##########################################\n\n"
        source = 'bitdb-query'
        LOGGER.info(f"{divider}REQUESTING TRANSACTIONS COUNT TO {source.upper()} | BLOCK: {block.number}{divider}")
        
        obj = bitdb_scanner.BitDB()
        total = obj.get_transactions_count(block.number)
        block.transactions_count = total
        block.currentcount = 0
        block.save()
        REDIS_STORAGE.set('BITDBQUERY_TOTAL', total)
        REDIS_STORAGE.set('BITDBQUERY_COUNT', 0)
        
        LOGGER.info(f"{divider}{source.upper()} FOUND {total} TRANSACTIONS {divider}")

        skip = 0
        complete = False
        page = 1
        
        while not complete:
            obj = bitdb_scanner.BitDB()
            source = 'bitdb-query'
            total_page = math.ceil(total/settings.BITDB_QUERY_LIMIT_PER_PAGE)
            
            LOGGER.info(f"{divider}REQUESTING TO {source.upper()} | BLOCK: {block.number}\nPAGE {int(page)} of {int(total_page)}{divider}")

            last, data = obj.get_transactions_by_blk(int(block.number), skip, settings.BITDB_QUERY_LIMIT_PER_PAGE)
            
            
            for transaction in data:
                res = bitdbquery_transaction.delay(transaction, total, block.number, block_id)
            
            if last:
                complete = True
            else:
                page += 1
                skip += settings.BITDB_QUERY_LIMIT_PER_PAGE
        
        
        processed_all = False
        while not processed_all:
            currentcount  = int(REDIS_STORAGE.get('BITDBQUERY_COUNT'))
            LOGGER.info(f"THERE ARE {currentcount} SUCCEEDED OUT OF {total} TASKS.")
            if currentcount == total:
                block = BlockHeight.objects.get(id=block_id)
                block.currentcount = currentcount
                block.save()
                REDIS_STORAGE.set('READY', 1)
                REDIS_STORAGE.set('ACTIVE-BLOCK', '')
                processed_all = True
            time.sleep(1)
        

    except bitdb_scanner.BitDBHttpException:
        try:
            self.retry(countdown=10)
        except MaxRetriesExceededError:
            pending_blocks = json.loads(REDIS_STORAGE.get('PENDING-BLOCKS'))
            pending_blocks.append(block.number)
            REDIS_STORAGE.set('PENDING-BLOCKS', json.dumps(pending_blocks))
            REDIS_STORAGE.set('READY', 1)

@shared_task(bind=True, queue='slpdbquery_transactions')
def slpdbquery_transaction(self, transaction, tx_count, total):
    source = 'slpdb-query'

    block_id = int(REDIS_STORAGE.get('BLOCK_ID'))
    block = BlockHeight.objects.get(id=block_id)
    
    if transaction['slp']['valid']:
        if transaction['slp']['detail']['transactionType'].lower() in ['send', 'mint', 'burn']:
            token_id = transaction['slp']['detail']['tokenIdHex']
            token, _ = Token.objects.get_or_create(tokenid=token_id)
            if transaction['slp']['detail']['outputs'][0]['address'] is not None:
                
                index = 1
                for output in transaction['slp']['detail']['outputs']:
                    subscription = check_wallet_address_subscription(output['address'])
                    LOGGER.info(f" * SOURCE: {source.upper()} | BLOCK {block.number} | TX: {transaction['tx']['h']} | SLP: {output['address']} | {tx_count} OUT OF {total}")
                    
                    # Disregard slp address that are not subscribed.
                    if subscription.exists():
                        obj_id, created = save_record(
                            token.tokenid,
                            output['address'],
                            transaction['tx']['h'],
                            output['amount'],
                            source,
                            blockheightid=block_id,
                            index=index
                        )
                        if created:
                            client_acknowledgement(obj_id)
                    index += 1
                

                for _in in transaction['in']:
                    txid = _in['e']['h']
                    index= _in['e']['i']
                    input_scanner(txid, index, block_id=block_id)
    
        
@shared_task(bind=True, queue='slpdbquery', max_retries=20)
def slpdbquery(self, block_id):
    REDIS_STORAGE.set('BLOCK_ID', block_id)
    divider = "\n\n##########################################\n\n"

    block = BlockHeight.objects.get(id=block_id)
    prev = BlockHeight.objects.filter(number=block.number-1)

    if block.processed:
        REDIS_STORAGE.set('ACTIVE-BLOCK', '')
        REDIS_STORAGE.set('READY', 1)
        return  # Terminate here if processed already

    try:
        
        source = 'slpdb-query'    
        LOGGER.info(f"{divider}REQUESTING TO {source.upper()} | BLOCK: {block.number}{divider}")
        
        obj = slpdb_scanner.SLPDB()
        data = obj.get_transactions_by_blk(int(block.number))
        total = len(data)
        LOGGER.info(f"{divider}{source.upper()} WILL SERVE {total} SLP TRANSACTIONS {divider}")

        REDIS_STORAGE.set('SLPDBQUERY_TOTAL', total)
        REDIS_STORAGE.set('SLPDBQUERY_COUNT', 0)
        
        tx_count = 0
        for chunk in chunks(data, 1000):
            for transaction in chunk:
                tx_count += 1
                REDIS_STORAGE.set('SLPDBQUERY_COUNT', tx_count)
                slpdbquery_transaction.delay(transaction, tx_count, total)

        if len(data) == 0 or (total == tx_count):
            bitdbquery.delay(block_id)
            
    except slpdb_scanner.SLPDBHttpExcetion:
        try:
            self.retry(countdown=10)
        except MaxRetriesExceededError:
            pending_blocks = json.loads(REDIS_STORAGE.get('PENDING-BLOCKS'))
            pending_blocks.append(block.number)
            REDIS_STORAGE.set('PENDING-BLOCKS', json.dumps(pending_blocks))
            REDIS_STORAGE.set('READY', 1)


@shared_task(bind=True, queue='manage_block_transactions')
def manage_block_transactions(self):
    if b'READY' not in REDIS_STORAGE.keys(): REDIS_STORAGE.set('READY', 1)
    if b'ACTIVE-BLOCK' not in REDIS_STORAGE.keys(): REDIS_STORAGE.set('ACTIVE-BLOCK', '')
    if b'PENDING-BLOCKS' not in REDIS_STORAGE.keys(): REDIS_STORAGE.set('PENDING-BLOCKS', json.dumps([]))
    
    pending_blocks = REDIS_STORAGE.get('PENDING-BLOCKS')
    blocks = json.loads(pending_blocks)

    if int(REDIS_STORAGE.get('READY')): LOGGER.info('READY TO PROCESS ANOTHER BLOCK')
    if not blocks: return 'NO PENDING BLOCKS'
    
    if int(REDIS_STORAGE.get('READY')):
        active_block = blocks[0]

        REDIS_STORAGE.set('ACTIVE-BLOCK', active_block)
        REDIS_STORAGE.set('READY', 0)

        block = BlockHeight.objects.get(number=active_block)        
        slpdbquery.delay(block.id)

        if active_block in blocks:
            blocks.remove(active_block)
            blocks = list(set(blocks))  # Uniquify the list
            blocks.sort()  # Then sort, ascending
            pending_blocks = json.dumps(blocks)
            REDIS_STORAGE.set('PENDING-BLOCKS', pending_blocks)
    
    active_block = str(REDIS_STORAGE.get('ACTIVE-BLOCK'))
    if active_block: return f'REDIS IS TOO BUSY FOR BLOCK {str(active_block)}.'

@shared_task(bind=True, queue='get_latest_block')
def get_latest_block(self):
    # This task is intended to check new blockheight every 5 seconds through BitDB Query
    LOGGER.info('CHECKING THE LATEST BLOCK')
    obj = bitdb_scanner.BitDB()
    number = obj.get_latest_block()
    obj, created = BlockHeight.objects.get_or_create(number=number)
    if created: return f'*** NEW BLOCK { obj.number } ***'

