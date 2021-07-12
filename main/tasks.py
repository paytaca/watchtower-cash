import math, logging, json, time, requests
from watchtower.settings import MAX_RESTB_RETRIES
from bitcash.transaction import calc_txid
from celery import shared_task
from main.models import (
    BlockHeight, 
    Token, 
    Transaction,
    Recipient,
    Subscription,
    Address,
    Wallet,
    WalletHistory
)
from celery.exceptions import MaxRetriesExceededError 
from main.utils import slpdb as slpdb_scanner
from main.utils import bitdb as bitdb_scanner
from main.utils.wallet import HistoryParser
from django.db.utils import IntegrityError
from django.conf import settings
from django.db import transaction as trans
from celery import Celery
from main.utils.chunk import chunks
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from main.utils.queries.bchd import BCHDQuery
import base64


LOGGER = logging.getLogger(__name__)
REDIS_STORAGE = settings.REDISKV


@shared_task()
def add(x, y):
    return x + y


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
        subscriptions = Subscription.objects.filter(
            address=address             
        )

        if subscriptions.exists():
            
            for subscription in subscriptions:

                recipient = subscription.recipient
                websocket = subscription.websocket

                data = {
                    'amount': transaction.amount,
                    'address': transaction.address.address,
                    'source': 'WatchTower',
                    'token': transaction.token.tokenid,
                    'txid': transaction.txid,
                    'block': block,
                    'index': transaction.index
                }

                if recipient:
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
                                    \n Address: {transaction.address.address}
                                    \n Token: {transaction.token.name}
                                    \n Token ID: {transaction.token.tokenid}
                                    \n Amount: {transaction.amount}
                                    \nhttps://explorer.bitcoin.com/bch/tx/{transaction.txid}
                                """
                            else:
                                message=f"""<b>WatchTower Notification</b> ℹ️
                                    \n Address: {transaction.address.address}
                                    \n Amount: {transaction.amount} BCH
                                    \nhttps://explorer.bitcoin.com/bch/tx/{transaction.txid}
                                """

                            args = ('telegram' , message, recipient.telegram_id)
                            third_parties.append(args)
                            this_transaction.update(acknowledged=True)

                if websocket:
                    
                    tokenid = ''
                    room_name = transaction.address.address.replace(':','_')
                    room_name += f'_{tokenid}'
                    channel_layer = get_channel_layer()
                    async_to_sync(channel_layer.group_send)(
                        f"{room_name}", 
                        {
                            "type": "send_update",
                            "data": data
                        }
                    )
                    if transaction.address.address.startswith('simpleledger:'):
                        tokenid = transaction.token.tokenid
                        room_name += f'_{tokenid}'
                        channel_layer = get_channel_layer()
                        async_to_sync(channel_layer.group_send)(
                            f"{room_name}", 
                            {
                                "type": "send_update",
                                "data": data
                            }
                        )
    return third_parties


@shared_task(queue='save_record')
def save_record(token, transaction_address, transactionid, amount, source, blockheightid=None, index=0, new_subscription=False, spent_txids=[]):
    """
        token                : can be tokenid (slp token) or token name (bch)
        transaction_address  : the destination address where token had been deposited.
        transactionid        : transaction id generated over blockchain.
        amount               : the amount being transacted.
        source               : the layer that summoned this function (e.g SLPDB, Bitsocket, BitDB, SLPFountainhead etc.)
        blockheight          : an optional argument indicating the block height number of a transaction.
        index          : used to make sure that each record is unique based on slp/bch address in a given transaction_id
    """
    subscription = Subscription.objects.filter(
        address__address=transaction_address             
    )
    
    spent_txids_check = Transaction.objects.filter(txid__in=spent_txids)

    # We are only tracking outputs of either subscribed addresses or those of transactions
    # that spend previous transactions with outputs involving tracked addresses
    if not subscription.exists() and not spent_txids_check.exists():
        return None, None

    address_obj, _ = Address.objects.get_or_create(address=transaction_address)

    try:
        index = int(index)
    except TypeError as exc:
        index = 0

    with trans.atomic():
        
        transaction_created = False

        if token.lower() == 'bch':
            token_obj, _ = Token.objects.get_or_create(name=token)
        else:
            token_obj, created = Token.objects.get_or_create(tokenid=token)
            if created: get_token_meta_data.delay(token_obj.tokenid)

        try:

            #  USE FILTER AND BULK CREATE AS A REPLACEMENT FOR GET_OR_CREATE        
            tr = Transaction.objects.filter(
                txid=transactionid,
                address=address_obj,
                index=index,
            )
            
            if not tr.exists():

                transaction_data = {
                    'txid': transactionid,
                    'address': address_obj,
                    'token': token_obj,
                    'amount': amount,
                    'index': index,
                    'source': source
                }
                transaction_list = [Transaction(**transaction_data)]
                Transaction.objects.bulk_create(transaction_list)
                transaction_created = True
        except IntegrityError:
            return None, None

        transaction_obj = Transaction.objects.get(
            txid=transactionid,
            address=address_obj,
            token=token_obj,
            amount=amount,
            index=index
        )

        if blockheightid is not None:
            transaction_obj.blockheight_id = blockheightid
            if new_subscription:
                transaction_obj.acknowledged = True

            # Automatically update all transactions with block height.
            Transaction.objects.filter(txid=transactionid).update(blockheight_id=blockheightid)

        # Check if address belongs to a wallet
        if address_obj.wallet:
            transaction_obj.wallet = address_obj.wallet

        # Save updates and trigger post-save signals
        transaction_obj.save()
        
        return transaction_obj.id, transaction_created


@shared_task(bind=True, queue='bitdbquery_transactions')
def bitdbquery_transaction(self, transaction, total, block_number, block_id, alert=True):
    
    tx_count = int(REDIS_STORAGE.incr('BITDBQUERY_COUNT'))

    source = 'bitdb-query'
    
    txn_id = transaction['tx']['h']
    
    for out in transaction['out']: 
        args = tuple()
        amount = out['e']['v'] / 100000000
        index = out['e']['i']
        if 'a' in out['e'].keys():
            bchaddress = 'bitcoincash:' + str(out['e']['a'])
            subscription = Subscription.objects.filter(address__address=bchaddress)
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
                    if alert:
                        third_parties = client_acknowledgement(obj_id)
                        for platform in third_parties:
                            if 'telegram' in platform:
                                message = platform[1]
                                chat_id = platform[2]
                                send_telegram_message(message, chat_id)


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
                bitdbquery_transaction.delay(transaction, total, block.number, block_id)
            
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
def slpdbquery_transaction(self, transaction, tx_count, total, alert=True):
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
                    subscription = Subscription.objects.filter(
                        address__address=output['address']
                    )
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
                            if alert:
                                client_acknowledgement(obj_id)
                    index += 1
    
        
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

    if len(blocks) == 0:
        unscanned_blocks = BlockHeight.objects.filter(
            processed=False,
            requires_full_scan=True
        ).values_list('number', flat=True)
        REDIS_STORAGE.set('PENDING-BLOCKS', json.dumps(list(unscanned_blocks)))


    if int(REDIS_STORAGE.get('READY')): LOGGER.info('READY TO PROCESS ANOTHER BLOCK')
    if not blocks: return 'NO PENDING BLOCKS'
    
    discard_block = False
    if int(REDIS_STORAGE.get('READY')):
        try:
            active_block = blocks[0]
            block = BlockHeight.objects.get(number=active_block)
        except BlockHeight.DoesNotExist:
            discard_block = True   
    
        if active_block in blocks:
            blocks.remove(active_block)
            blocks = list(set(blocks))  # Uniquify the list
            blocks.sort()  # Then sort, ascending
            pending_blocks = json.dumps(blocks)
            REDIS_STORAGE.set('PENDING-BLOCKS', pending_blocks)

        if not discard_block:
            REDIS_STORAGE.set('ACTIVE-BLOCK', active_block)
            REDIS_STORAGE.set('READY', 0)
            slpdbquery.delay(block.id)     
    
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


@shared_task(bind=True, queue='get_utxos', max_retries=10)
def get_bch_utxos(self, address):
    try:
        obj = BCHDQuery()
        outputs = obj.get_utxos(address)
        source = 'bchd-query'
        saved_utxo_ids = []
        for output in outputs:
            hash = output.outpoint.hash 
            index = output.outpoint.index
            block = output.block_height
            tx_hash = bytearray(hash[::-1]).hex()
            amount = output.value / (10 ** 8)
            
            block, created = BlockHeight.objects.get_or_create(number=block)
            transaction_obj = Transaction.objects.filter(
                txid=tx_hash,
                address__address=address,
                amount=amount,
                index=index
            )
            if not transaction_obj.exists():
                args = (
                    'bch',
                    address,
                    tx_hash,
                    amount,
                    source,
                    block.id,
                    index,
                    True
                )
                txn_id, created = save_record(*args)
                transaction_obj = Transaction.objects.filter(id=txn_id)

                if created:
                    if not block.requires_full_scan:
                        qs = BlockHeight.objects.filter(id=block.id)
                        count = qs.first().transactions.count()
                        qs.update(processed=True, transactions_count=count)
            
            if transaction_obj.exists():
                # Mark as unspent, just in case it's already marked spent
                transaction_obj.update(spent=False)
                for obj in transaction_obj:
                    saved_utxo_ids.append(obj.id)

        # Mark other transactions of the same address as spent
        txn_check = Transaction.objects.filter(
            address__address=address,
            spent=False
        ).exclude(
            id__in=saved_utxo_ids
        ).update(
            spent=True
        )

    except Exception as exc:
        try:
            LOGGER.error(exc)
            self.retry(countdown=4)
        except MaxRetriesExceededError:
            LOGGER.error(f"CAN'T EXTRACT UTXOs OF {address} THIS TIME. THIS NEEDS PROPER FALLBACK.")


@shared_task(bind=True, queue='get_utxos', max_retries=10)
def get_slp_utxos(self, address):
    try:
        obj = BCHDQuery()
        outputs = obj.get_utxos(address)
        source = 'bchd-query'
        saved_utxo_ids = []
        for output in outputs:
            if output.slp_token.token_id:
                hash = output.outpoint.hash 
                tx_hash = bytearray(hash[::-1]).hex()
                index = output.outpoint.index
                token_id = bytearray(output.slp_token.token_id).hex() 
                amount = output.slp_token.amount / (10 ** output.slp_token.decimals)
                block = output.block_height
                
                block, _ = BlockHeight.objects.get_or_create(number=block)

                token_obj, _ = Token.objects.get_or_create(tokenid=token_id)

                transaction_obj = Transaction.objects.filter(
                    txid=tx_hash,
                    address__address=address,
                    token=token_obj,
                    amount=amount,
                    index=index
                )
                if not transaction_obj.exists():
                    args = (
                        token_id,
                        address,
                        tx_hash,
                        amount,
                        source,
                        block.id,
                        index,
                        True
                    )
                    txn_id, created = save_record(*args)
                    transaction_obj = Transaction.objects.filter(id=txn_id)
                    
                    if created:
                        if not block.requires_full_scan:
                            qs = BlockHeight.objects.filter(id=block.id)
                            count = qs.first().transactions.count()
                            qs.update(processed=True, transactions_count=count)
                
                if transaction_obj.exists():
                    # Mark as unspent, just in case it's already marked spent
                    transaction_obj.update(spent=False)
                    for obj in transaction_obj:
                        saved_utxo_ids.append(obj.id)
        
        # Mark other transactions of the same address as spent
        txn_check = Transaction.objects.filter(
            address__address=address,
            spent=False
        ).exclude(
            id__in=saved_utxo_ids
        ).update(
            spent=True
        )

    except Exception as exc:
        try:
            LOGGER.error(exc)
            self.retry(countdown=4)
        except MaxRetriesExceededError:
            LOGGER.error(f"CAN'T EXTRACT UTXOs OF {address} THIS TIME. THIS NEEDS PROPER FALLBACK.")


@shared_task(bind=True, queue='token_metadata', max_retries=10)
def get_token_meta_data(self, token_id):
    try:
        bchd = BCHDQuery()
        txn = bchd.get_transaction(token_id, parse_slp=True)
        info = txn['token_info']
        group_check = Token.objects.filter(tokenid=info['nft_token_group'])
        if group_check.exists():
            group = group_check.first()
        else:
            group = Token(tokenid=info['nft_token_group'])
            group.save()
        Token.objects.filter(tokenid=token_id).update(
            name=info['name'],
            token_ticker=info['ticker'],
            token_type=info['type'],
            nft_token_group=group,
            decimals=info['decimals']
        )
    except Exception:
        self.retry(countdown=5)


@shared_task(bind=True, queue='broadcast', max_retries=10)
def broadcast_transaction(self, transaction):
    txid = calc_txid(transaction)
    LOGGER.info(f'Broadcasting {txid}:  {transaction}')
    txn_check = Transaction.objects.filter(txid=txid)
    if txn_check.exists():
        return True, txid
    else:
        try:
            obj = BCHDQuery()
            try:
                txid = obj.broadcast_transaction(transaction)
                if txid:
                    return True, txid
                else:
                    self.retry(countdown=1)
            except Exception as exc:
                error = exc.details()
                LOGGER.error(error)
                return False, error
        except AttributeError:
            self.retry(countdown=1)


@shared_task(bind=True, queue='post_save_record')
def parse_wallet_history(self, txid, wallet_hash):
    parser = HistoryParser(txid, wallet_hash)
    record_type, amount = parser.parse()
    wallet = Wallet.objects.get(wallet_hash=wallet_hash)
    if wallet.wallet_type == 'bch':
        txns = Transaction.objects.filter(
            txid=txid,
            address__address__startswith='bitcoincash:'
        )
    elif wallet.wallet_type == 'slp':
        txns = Transaction.objects.filter(
            txid=txid,
            address__address__startswith='simpleledger:'
        )
    txn = txns.last()
    if txn:
        history_check = WalletHistory.objects.filter(
            wallet=wallet,
            txid=txid
        )
        if history_check.exists():
            history_check.update(
                record_type=record_type,
                amount=amount,
                token=txn.token
            )
        else:
            history = WalletHistory(
                wallet=wallet,
                txid=txid,
                record_type=record_type,
                amount=amount,
                token=txn.token,
                date_created=txn.date_created
            )
            history.save()


@shared_task(bind=True, queue='post_save_record', max_retries=10)
def transaction_post_save_task(self, address, txid, blockheight_id=None):
    blockheight = None
    if blockheight_id:
        blockheight = BlockHeight.objects.get(id=blockheight_id)

    wallets = []
    txn_address = Address.objects.get(address=address)
    if txn_address.wallet:
        wallets.append(txn_address.wallet.wallet_hash)

    if address.startswith('bitcoincash:'):
        # Make sure that any corresponding SLP transaction is saved
        bchd = BCHDQuery()
        slp_tx = bchd.get_transaction(txid, parse_slp=True)

        spent_txids = []

        # Mark inputs as spent
        for tx_input in slp_tx['inputs']:
            try:
                address = Address.objects.get(address=tx_input['address'])
                if address.wallet:
                    wallets.append(address.wallet.wallet_hash)
            except Address.DoesNotExist:
                pass
            spent_txids.append(tx_input['txid'])
            txn_check = Transaction.objects.filter(
                txid=tx_input['txid'],
                index=tx_input['spent_index']
            )
            txn_check.update(
                spent=True,
                spending_txid=txid
            )

        if slp_tx['valid']:
            for tx_output in slp_tx['outputs']:
                try:
                    address = Address.objects.get(address=tx_output['address'])
                    if address.wallet:
                        wallets.append(address.wallet.wallet_hash)
                except Address.DoesNotExist:
                    pass
                txn_check = Transaction.objects.filter(
                    txid=slp_tx['txid'],
                    address__address=tx_output['address'],
                    index=tx_output['index']
                )
                if not txn_check.exists():
                    blockheight_id = None
                    if blockheight:
                        blockheight_id = blockheight.id
                    args = (
                        slp_tx['token_id'],
                        tx_output['address'],
                        slp_tx['txid'],
                        tx_output['amount'],
                        'bchd-query',
                        blockheight_id,
                        tx_output['index']
                    )
                    obj_id, created = save_record(*args, spent_txids=spent_txids)
                    if created:
                        third_parties = client_acknowledgement(obj_id)
                        for platform in third_parties:
                            if 'telegram' in platform:
                                message = platform[1]
                                chat_id = platform[2]
                                send_telegram_message(message, chat_id)

    elif address.startswith('simpleledger:'):
        # Make sure that any corresponding BCH transaction is saved
        bchd = BCHDQuery()
        txn = bchd.get_transaction(txid)

        spent_txids = []
        
        # Mark inputs as spent
        for tx_input in txn['inputs']:
            try:
                address = Address.objects.get(address=tx_input['address'])
                if address.wallet:
                    wallets.append(address.wallet.wallet_hash)
            except Address.DoesNotExist:
                pass

            spent_txids.append(tx_input['txid'])
            txn_check = Transaction.objects.filter(
                txid=tx_input['txid'],
                index=tx_input['spent_index']
            )
            txn_check.update(
                spent=True,
                spending_txid=txid
            )

        for tx_output in txn['outputs']:
            try:
                address = Address.objects.get(address=tx_output['address'])
                if address.wallet:
                    wallets.append(address.wallet.wallet_hash)
            except Address.DoesNotExist:
                pass
            txn_check = Transaction.objects.filter(
                txid=txn['txid'],
                address__address=tx_output['address'],
                index=tx_output['index']
            )
            if not txn_check.exists():
                blockheight_id = None
                if blockheight:
                    blockheight_id = blockheight.id
                value = tx_output['value'] / 10 ** 8
                args = (
                    'bch',
                    tx_output['address'],
                    txn['txid'],
                    value,
                    'bchd-query',
                    blockheight_id,
                    tx_output['index']
                )
                obj_id, created = save_record(*args, spent_txids=spent_txids)
                if created:
                    third_parties = client_acknowledgement(obj_id)
                    for platform in third_parties:
                        if 'telegram' in platform:
                            message = platform[1]
                            chat_id = platform[2]
                            send_telegram_message(message, chat_id)

    # Call task to parse wallet history
    for wallet_hash in set(wallets):
        parse_wallet_history.delay(txid, wallet_hash)
