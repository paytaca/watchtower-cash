import logging, json, requests
import pytz
from decimal import Decimal
from datetime import datetime
from urllib.parse import urlparse
from django.db import models
from watchtower.settings import MAX_RESTB_RETRIES
from bitcash.transaction import calc_txid
from celery import shared_task
from main.models import *
from main.utils.address_validator import *
from main.utils.ipfs import (
    get_ipfs_cid_from_url,
    ipfs_gateways,
)
from main.utils.purelypeer import is_key_nft
from main.utils.market_price import (
    fetch_currency_value_for_timestamp,
    get_latest_bch_rates,
    save_wallet_history_currency,
)
from celery.exceptions import MaxRetriesExceededError 
from main.utils.nft import (
    find_token_utxo,
    find_minting_baton,
)
from main.utils.address_converter import bch_address_converter
from main.utils.address_validator import is_bch_address
from main.utils.wallet import HistoryParser
from main.utils.push_notification import (
    send_wallet_history_push_notification,
)
from django.db.utils import IntegrityError
from django.conf import settings
from django.utils import timezone, dateparse
from django.db import transaction as trans
from celery import Celery
from main.utils.chunk import chunks
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from main.utils.queries.node import Node
from main.utils.queries.parse_utils import (
    parse_utxo_to_tuple,
    extract_tx_utxos,
)
from PIL import Image, ImageFile
from io import BytesIO 
import pytz
from celery import chord

LOGGER = logging.getLogger(__name__)
REDIS_STORAGE = settings.REDISKV
NODE = Node()


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

        senders = [*Transaction.objects.filter(spending_txid=transaction.txid).values_list('address__address', flat=True)]

        if subscriptions.exists():
            
            for subscription in subscriptions:

                recipient = subscription.recipient
                websocket = subscription.websocket

                wallet_version = 1
                if address.wallet:
                    wallet_version = address.wallet.version
                else:
                    # Hardcoded date-based check for addresses that are not associated with wallets
                    v2_rollout_date_str = dateparse.parse_datetime('2021-09-11 00:00:00')
                    v2_rollout_date = pytz.UTC.localize(v2_rollout_date_str)
                    if address.date_created >= v2_rollout_date:
                        wallet_version = 2


                token_name = transaction.token.name
                token_id = transaction.token.info_id
                token_decimals = transaction.token.decimals
                token_symbol = transaction.token.token_ticker.lower()
                
                token = None
                image_url = None
                token_details_key = None
                __is_key_nft = False
                lock_nft_category = None

                if transaction.cashtoken_ft:
                    token = transaction.cashtoken_ft
                    token_details_key = 'fungible'
                elif transaction.cashtoken_nft:
                    token = transaction.cashtoken_nft
                    token_details_key = 'nft'
                    category = token.token_id.split('/')[1]
                    __is_key_nft, lock_nft_category = is_key_nft(subscription.address, category)

                if transaction.cashtoken_ft or transaction.cashtoken_nft:
                    token_default_details = settings.DEFAULT_TOKEN_DETAILS[token_details_key]
                    token_id = token.token_id
                    token_name = token_default_details['name']
                    token_symbol = token_default_details['symbol']
                    token_decimals = 0
                    
                    if token.info:
                        token_name = token.info.name
                        token_symbol = token.info.symbol
                        token_decimals = token.info.decimals
                        image_url = token.info.image_url
                
                txn_amount = None
                if transaction.amount:
                    txn_amount = str(transaction.amount)

                if wallet_version == 2:
                    data = {
                        'token_name': token_name,
                        'token_id':  token_id,
                        'token_symbol': token_symbol,
                        'token_decimals': token_decimals,
                        'image_url': image_url,
                        'amount': txn_amount,
                        'value': transaction.value,
                        'address': transaction.address.address,
                        'source': 'WatchTower',
                        'txid': transaction.txid,
                        'block': block,
                        'index': transaction.index,
                        'address_path' : transaction.address.address_path,
                        'senders': senders,
                        'is_nft': False,
                        'purelypeer': {
                            'is_key_nft': __is_key_nft,
                            'lock_nft_category': None
                        }
                    }

                    if transaction.cashtoken_nft:
                        data['capability'] = token.capability
                        data['commitment'] = token.commitment
                        data['id'] = token.id
                        data['is_nft'] = True

                    if __is_key_nft:
                        data['purelypeer']['lock_nft_category'] = lock_nft_category

                elif wallet_version == 1:
                    data = {
                        'amount': txn_amount,
                        'value': transaction.value,
                        'address': transaction.address.address,
                        'source': 'WatchTower',
                        'token': transaction.token.tokenid or transaction.token.token_ticker.lower(),
                        'txid': transaction.txid,
                        'block': block,
                        'index': transaction.index,
                        'address_path' : transaction.address.address_path
                    }

                if recipient:
                    if recipient.valid:
                        if recipient.web_url:
                            LOGGER.info(f"Webhook call to be sent to: {recipient.web_url}")
                            LOGGER.info(f"Data: {str(data)}")
                            resp = requests.post(recipient.web_url,data=data)
                            if resp.status_code == 200:
                                this_transaction.update(acknowledged=True)
                                LOGGER.info(f'ACKNOWLEDGEMENT SENT TX INFO : {transaction.txid} TO: {recipient.web_url} DATA: {str(data)}')
                            elif resp.status_code == 404 or resp.status_code == 522 or resp.status_code == 502:
                                Recipient.objects.filter(id=recipient.id).update(valid=False)
                                LOGGER.info(f"!!! ATTENTION !!! THIS IS AN INVALID DESTINATION URL: {recipient.web_url}")
                            else:
                                LOGGER.error(resp)
                                self.retry(countdown=3)

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
                    if transaction.token:
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


def get_cashtoken_meta_data(
    category,
    txid=None,
    index=None,
    is_nft=False,
    commitment=None,
    capability=None,
    from_bcmr_webhook=False
):
    LOGGER.info(f'Fetching cashtoken metadata for {category} from BCMR')

    METADATA = None
    detail_key = 'nft' if is_nft else 'fungible'
    default_details = settings.DEFAULT_TOKEN_DETAILS[detail_key]

    # TODO: Don't fetch from BCMR indexer for now, to be reconsidered later
    # PAYTACA_BCMR_URL = f'{settings.PAYTACA_BCMR_URL}/tokens/{category}/'
    # response = requests.get(PAYTACA_BCMR_URL)

    # if response.status_code == 200:
    #     METADATA = response.json()
    #     if "error" in METADATA:
    #         METADATA = None

    if METADATA:
        name = METADATA['name'] or default_details['name']
        description = METADATA['description']
        symbol = METADATA['symbol'] or default_details['symbol']
        decimals = METADATA['decimals']
        image_url = METADATA['uris']['icon']
        
        # nft_details field for FT are {}
        # nft_details field for NFTs are:
        #   if minting: nft_details = children types or {}
        #   else: nft_details = child type details (to include extensions and other data) or {}
        nfts = None

        if is_nft:
            _capability = capability.lower()
            types = METADATA['types']

            if _capability == 'minting':
                nfts = types
            else:
                if types:
                    if commitment in types.keys():
                        nfts = types[commitment]
                        nft_keys = nfts.keys()

                        if 'name' in nft_keys:
                            name = nfts['name']
                        if 'description' in nft_keys:
                            description = nfts['description']
                        if 'uris' in nft_keys:
                            uris = nfts['uris']
                            if 'icon' in uris.keys():
                                image_url = uris['icon']
        data = {
            'name': name,
            'description': description,
            'symbol': symbol,
            'decimals': decimals,
            'image_url': image_url
        }

        if nfts:
            data['nft_details'] = nfts
        
        # did not use get_or_create bec of async multiple objects returned error
        cashtoken_infos = CashTokenInfo.objects.filter(**data)
        if cashtoken_infos.exists():
            cashtoken_info = cashtoken_infos.first()
        else:
            cashtoken_info = CashTokenInfo(**data)
            cashtoken_info.save()
    else:
        # save as default metadata/info if there is no record of metadata from BCMR
        name = default_details['name']
        symbol = default_details['symbol']
            
        # did not use get_or_create bec of async multiple objects returned error
        cashtoken_infos = CashTokenInfo.objects.filter(name=name, symbol=symbol)
        if cashtoken_infos.exists():
            cashtoken_info = cashtoken_infos.first()
        else:
            cashtoken_info = CashTokenInfo(name=name, symbol=symbol)
            cashtoken_info.save()

    if is_nft:
        if from_bcmr_webhook:
            nfts = CashNonFungibleToken.objects.filter(
                category=category,
                commitment=commitment
            )
            nfts.update(info=cashtoken_info)

        cashtoken, _ = CashNonFungibleToken.objects.get_or_create(
            current_index=index,
            current_txid=txid
        )
        cashtoken.category = category
        cashtoken.commitment = commitment
        cashtoken.capability = capability
        cashtoken.info = cashtoken_info
        cashtoken.save()
    else:
        cashtoken, _ = CashFungibleToken.objects.get_or_create(category=category)
        cashtoken.fetch_metadata()

    return cashtoken


@shared_task(queue='save_record')
def save_record(
    token,
    transaction_address,
    transactionid,
    source,
    amount=None,
    value=0,
    blockheightid=None,
    index=0,
    new_subscription=False,
    spent_txids=[],
    inputs=None,
    spending_txid=None,
    tx_timestamp=None,
    force_create=False,
    is_cashtoken=False,
    is_cashtoken_nft=False,
    capability='',
    commitment=''
):
    """
        token                : can be tokenid (slp token) or token name (bch) or category (cashtoken)
        transaction_address  : the destination address where token had been deposited.
        transactionid        : transaction id generated over blockchain.
        amount               : the amount being transacted.
        source               : the layer that summoned this function (e.g SLPDB, Bitsocket, BitDB, SLPFountainhead etc.)
        blockheight          : an optional argument indicating the block height number of a transaction.
        index                : used to make sure that each record is unique based on slp/bch address in a given transaction_id
        tx_timestamp         : unix timestamp of transaction
        inputs               : an array of dicts containing data on the transaction's inputs
                               example: {
                                    "index": 0,
                                    "token": "bch",
                                    "address": "",
                                    "amount": 0,
                                    "outpoint_txid": "",
                                    "outpoint_index": 0,
                                }
        is_cashtoken         : determines if a fungible token or NFT is CashToken (True) or SLP (False)
        is_cashtoken_nft     : supply this param if is_cashtoken is True
        capability           : minting/mutable/immutable for cashtoken NFTs
        commitment           : special hex/embedded string for cashtoken NFTs
        value                : value of transaction (amount = value in BCH, value = varies on tokens)
    """

    subscription = Subscription.objects.filter(
        address__address=transaction_address             
    )

    # We are only tracking outputs of either subscribed addresses or those of transactions
    # that spend previous transactions with outputs involving tracked addresses
    if not subscription.exists() and not force_create:
        return None, None

    address_obj, _ = Address.objects.get_or_create(address=transaction_address)

    try:
        index = int(index)
    except TypeError as exc:
        index = 0

    with trans.atomic():
        transaction_created = False
        cashtoken = None

        if token.lower() == 'bch':
            token_obj, created = Token.objects.get_or_create(name=token)
            
            if created:
                token_obj.token_ticker = 'bch'
                token_obj.decimals = 8
                token_obj.token_type = 1
                token_obj.save()
        else:
            if is_cashtoken:
                token_obj, created = Token.objects.get_or_create(tokenid=settings.WT_DEFAULT_CASHTOKEN_ID)
                
                if created:
                    token_obj.name = 'CashToken - '
                    token_obj.token_ticker = 'CT-' + token_obj.tokenid[0:6]
                    token_obj.save()
                
                # get cashtoken metadata always in case there are changes on BCMR
                cashtoken = get_cashtoken_meta_data(
                    token,
                    txid=transactionid,
                    index=index,
                    commitment=commitment,
                    capability=capability,
                    is_nft=is_cashtoken_nft
                )
            else:
                token_obj, created = Token.objects.get_or_create(tokenid=token)
                if created:
                    get_token_meta_data.delay(token)

        # try:

        #     #  USE FILTER AND BULK CREATE AS A REPLACEMENT FOR GET_OR_CREATE        
        #     tr = Transaction.objects.filter(
        #         txid=transactionid,
        #         address=address_obj,
        #         index=index,
        #     )
            
        #     if not tr.exists():

        #         transaction_data = {
        #             'txid': transactionid,
        #             'address': address_obj,
        #             'token': token_obj,
        #             'amount': amount,
        #             'index': index,
        #             'source': source
        #         }
        #         transaction_list = [Transaction(**transaction_data)]
        #         Transaction.objects.bulk_create(transaction_list)
        #         transaction_created = True
        # except IntegrityError:
        #     return None, None

        try:
            txn_data = {
                'txid': transactionid,
                'address': address_obj,
                'token': token_obj,
                'index': index
            }
            if is_cashtoken:
                if is_cashtoken_nft:
                    txn_data['cashtoken_nft'] = CashNonFungibleToken.objects.get(id=cashtoken.id)
                else:
                    txn_data['cashtoken_ft'] = CashFungibleToken.objects.get(category=cashtoken.category)

            transaction_obj, transaction_created = Transaction.objects.get_or_create(**txn_data)
            transaction_obj.amount = amount
            transaction_obj.value = int(value)

            if spending_txid:
                transaction_obj.spending_txid = spending_txid
                transaction_obj.spent = True

            if transaction_obj.source != source:
                transaction_obj.source = source

            if tx_timestamp:
                transaction_obj.tx_timestamp = datetime.fromtimestamp(tx_timestamp).replace(tzinfo=pytz.UTC)

        except IntegrityError as exc:
            LOGGER.error('ERROR in saving txid: ' + transactionid)
            LOGGER.error(str(exc))
            return None, None

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
        
        # save the transaction_obj's inputs if provided
        if inputs is not None:
            for tx_input in inputs:
                save_record(
                    tx_input["token"],
                    tx_input["address"],
                    tx_input["outpoint_txid"],
                    source,
                    # amount=tx_input["amount"],
                    value=tx_input["value"],
                    index=tx_input["outpoint_index"],
                    spending_txid=transaction_obj.txid,
                    force_create=True
                )
        return transaction_obj.id, transaction_created


def process_cashtoken_tx(
    token_data,
    address,
    txid,
    block_id=None,
    index=0,
    timestamp=None,
    force_create=False,
    value=0
):
    token_id = token_data['category']

    amount = None
    if 'amount' in token_data.keys():
        amount = amount = int(token_data['amount'])

    created = False
    # save nft transaction
    if 'nft' in token_data.keys():
        nft_data = token_data['nft']
        capability = nft_data['capability']
        commitment = nft_data['commitment']

        obj_id, created = save_record(
            token_id,
            address,
            txid,
            NODE.BCH.source,
            amount=amount,
            value=value,
            blockheightid=block_id,
            tx_timestamp=timestamp,
            index=index,
            is_cashtoken=True,
            is_cashtoken_nft=True,
            capability=capability,
            commitment=commitment,
            force_create=force_create
        )
    else:
        # save fungible token transaction
        obj_id, created = save_record(
            token_id,
            address,
            txid,
            NODE.BCH.source,
            amount=amount,
            value=value,
            blockheightid=block_id,
            tx_timestamp=timestamp,
            index=index,
            is_cashtoken=True,
            force_create=force_create
        )

    decimals = None
    if created:
        txn_obj = Transaction.objects.get(id=obj_id)
        decimals = txn_obj.get_token_decimals()

        client_acknowledgement(obj_id)
    
    return {
        'created': created,
        'token_id': 'ct/' + token_id,
        'decimals': decimals,
        'amount': amount or ''
    }

@shared_task(queue='query_transaction')
def query_transaction(txid, block_id, for_slp=False):
    if for_slp:
        transaction = NODE.SLP._get_raw_transaction(txid)

        for output in transaction.outputs:
            if output.slp_token.token_id:
                token_id = bytearray(output.slp_token.token_id).hex()
                amount = output.slp_token.amount
                # save slp transaction
                obj_id, created = save_record(
                    token_id,
                    'simpleledger:%s' % output.slp_token.address,
                    txid,
                    NODE.SLP.source,
                    amount=amount,
                    blockheightid=block_id,
                    tx_timestamp=transaction.timestamp,
                    index=output.index
                )            
                if created:
                    client_acknowledgement(obj_id)
                
    else:
        transaction = NODE.BCH._get_raw_transaction(txid)

        if 'coinbase' in transaction['vin'][0].keys():
            return

        for output in transaction['vout']:
            index = output['n']

            if 'addresses' in output['scriptPubKey'].keys():
                address = output['scriptPubKey']['addresses'][0]
                value = int(output['value'] * (10 ** 8))
                
                if 'tokenData' in output.keys():
                    process_cashtoken_tx(
                        output['tokenData'],
                        address,
                        txid,
                        block_id=block_id,
                        index=index,
                        timestamp=transaction['time'],
                        value=value
                    )
                else:
                    # save bch transaction
                    obj_id, created = save_record(
                        'bch',
                        address,
                        txid,
                        NODE.BCH.source,
                        value=value,
                        blockheightid=block_id,
                        tx_timestamp=transaction['time'],
                        index=index
                    )
                    if created:
                        client_acknowledgement(obj_id)


@shared_task(bind=True, queue='manage_blocks')
def ready_to_accept(self, block_number, txs_count):
    BlockHeight.objects.filter(number=block_number).update(
        processed=True,
        transactions_count=txs_count,
        updated_datetime=timezone.now()
    )
    REDIS_STORAGE.set('READY', 1)
    REDIS_STORAGE.set('ACTIVE-BLOCK', '')
    return 'OK'


@shared_task(bind=True, queue='manage_blocks')
def manage_blocks(self):
    if b'READY' not in REDIS_STORAGE.keys(): REDIS_STORAGE.set('READY', 1)
    if b'ACTIVE-BLOCK' not in REDIS_STORAGE.keys(): REDIS_STORAGE.set('ACTIVE-BLOCK', '')
    if b'PENDING-BLOCKS' not in REDIS_STORAGE.keys(): REDIS_STORAGE.set('PENDING-BLOCKS', json.dumps([]))
    
    pending_blocks = REDIS_STORAGE.get('PENDING-BLOCKS').decode()
    blocks = json.loads(pending_blocks)
    blocks.sort()

    if len(blocks) == 0:
        unscanned_blocks = BlockHeight.objects.filter(
            processed=False,
            requires_full_scan=True
        ).values_list('number', flat=True)
        blocks = list(unscanned_blocks)
        REDIS_STORAGE.set('PENDING-BLOCKS', json.dumps(blocks))


    if int(REDIS_STORAGE.get('READY').decode()): LOGGER.info('READY TO PROCESS ANOTHER BLOCK')
    if not blocks: return 'NO PENDING BLOCKS'
    
    discard_block = False
    if int(REDIS_STORAGE.get('READY').decode()):
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
            try:
                # TODO: handle block tracking for SLP testnet when BCH_NETWORK=chipnet
                # (testnet has different block count with chipnet)
                if settings.BCH_NETWORK == 'mainnet':
                    pass
                    
                    #TODO: Disable block scanning in SLP, for now
                    # transactions = NODE.SLP.get_block(block.number, full_transactions=False)
                    # for tr in transactions:
                    #     txid = bytearray(tr.transaction_hash[::-1]).hex()
                    #     subtasks.append(query_transaction.si(txid, block.id, for_slp=True))

                transactions = NODE.BCH.get_block(block.number, verbosity=3)
                block_time = NODE.BCH.get_block_stats(block.number, stats=["time"])["time"]
                for tx in transactions:
                    tx["time"] = block_time # tx is from .get_block() which doesn't return tx's timestamp
                    parsed_tx = NODE.BCH._parse_transaction(tx)
                    save_transaction(parsed_tx, block_id=block.id)

                ready_to_accept.delay(block.number, len(transactions))
            finally:
                REDIS_STORAGE.set('READY', 1)

    active_block = str(REDIS_STORAGE.get('ACTIVE-BLOCK').decode())
    if active_block: return f'CURRENTLY PROCESSING BLOCK {str(active_block)}.'


def save_transaction(tx, block_id=None):
    """
        tx must be parsed by 'BCHN._parse_transaction()'
    """
    txid = tx['txid']
    if 'coinbase' in tx['inputs'][0].keys():
        return

    for output in tx['outputs']:
        index = output['index']
        address = output['address']
        value = output['value']

        if output.get('token_data'):
            process_cashtoken_tx(
                output['token_data'],
                address,
                txid,
                block_id=block_id,
                index=index,
                timestamp=tx['timestamp'],
                value=value
            )
        else:
            # save bch transaction
            obj_id, created = save_record(
                'bch',
                address,
                txid,
                NODE.BCH.source,
                value=value,
                blockheightid=block_id,
                tx_timestamp=tx['timestamp'],
                index=index
            )
            if created:
                client_acknowledgement(obj_id)


@shared_task(bind=True, queue='get_latest_block')
def get_latest_block(self):
    # This task is intended to check new blockheight every 5 seconds
    LOGGER.info('CHECKING THE LATEST BLOCK')
    number = NODE.BCH.get_latest_block()
    obj, created = BlockHeight.objects.get_or_create(number=number)
    if created: return f'*** NEW BLOCK { obj.number } ***'


@shared_task(bind=True, queue='get_utxos', max_retries=10)
def get_bch_utxos(self, address):
    try:
        outputs = NODE.BCH.get_utxos(address)
        saved_utxo_ids = []
        
        for output in outputs:
            index = output['tx_pos']
            block = output['height']
            tx_hash = output['tx_hash']
            is_nft = False
            is_cashtoken = False
            commitment = ''
            capability = ''
            value = output['value']
            amount = None

            if 'token_data' in output.keys():
                token_data = output['token_data']
                token_id = token_data['category']
                is_cashtoken = True

                if 'amount' in token_data.keys():
                    amount = int(token_data['amount'])

                if 'nft' in token_data.keys():
                    is_nft = True
                    capability = token_data['nft']['capability']
                    commitment = token_data['nft']['commitment']
            else:
                token_id = 'bch'

            block, created = BlockHeight.objects.get_or_create(number=block)
            transaction_obj = Transaction.objects.filter(
                txid=tx_hash,
                address__address=address,
                value=value,
                index=index
            )
            if not transaction_obj.exists():
                txn_id, created = save_record(
                    token_id,
                    address,
                    tx_hash,
                    NODE.BCH.source,
                    value=value,
                    amount=amount,
                    blockheightid=block.id,
                    index=index,
                    new_subscription=True,
                    is_cashtoken=is_cashtoken,
                    is_cashtoken_nft=is_nft,
                    commitment=commitment,
                    capability=capability
                )
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
        outputs = NODE.SLP.get_utxos(address)
        saved_utxo_ids = []

        for output in outputs:
            if output.slp_token.token_id:
                hash = output.outpoint.hash 
                tx_hash = bytearray(hash[::-1]).hex()
                index = output.outpoint.index
                token_id = bytearray(output.slp_token.token_id).hex() 
                amount = output.slp_token.amount
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
                        NODE.SLP.source
                    )
                    txn_id, created = save_record(
                        *args,
                        amount=amount,
                        blockheightid=block.id,
                        index=index,
                        new_subscription=True
                    )
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


def is_url(url):
  try:
    result = urlparse(url)
    return all([result.scheme, result.netloc])
  except ValueError:
    return False


def download_image(token_id, url, resize=False):
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    resp = requests.get(url, stream=True, timeout=300)
    image_file_name = None
    if resp.status_code == 200:
        content_type = resp.headers.get('content-type')
        if content_type.split('/')[0] == 'image':
            file_ext = content_type.split('/')[1]

            img = Image.open(BytesIO(resp.content))
            if resize:
                LOGGER.info('Saving resized images...')
                # Save medium size
                width, height = img.size
                medium_width = 450
                medium_height = medium_width * (height / width)
                medium_size = (medium_width, int(medium_height))
                medium_img = img.resize(medium_size, Image.ANTIALIAS)
                out_path = f"{settings.TOKEN_IMAGES_DIR}/{token_id}_medium.{file_ext}"
                medium_img.save(out_path, quality=95)
                LOGGER.info(out_path)

                # Save thumbnail size
                thumbnail_width = 150
                thumbnail_height = thumbnail_width * (height / width)
                thumbnail_size = (thumbnail_width, int(thumbnail_height))
                thumbnail_img = img.resize(thumbnail_size, Image.ANTIALIAS)
                out_path = f"{settings.TOKEN_IMAGES_DIR}/{token_id}_thumbnail.{file_ext}"
                thumbnail_img.save(out_path, quality=95)
                LOGGER.info(out_path)

            # Save original size
            LOGGER.info('Saving original image...')
            out_path = f"{settings.TOKEN_IMAGES_DIR}/{token_id}.{file_ext}"
            LOGGER.info(out_path)
            img.save(out_path, quality=95)
            image_file_name = f"{token_id}.{file_ext}"
            LOGGER.info(f"Saved image for token {token_id} from {url}")

    return resp.status_code, image_file_name


@shared_task(queue='token_metadata', max_retries=3)
def download_token_metadata_image(token_id, document_url=None):
    token_obj = Token.objects.get(tokenid=token_id)

    image_server_base = 'https://images.watchtower.cash'
    image_file_name = None
    image_url = None
    status_code = 0

    if token_obj.token_type == 1:
        # Check slp-token-icons repo
        url = f"https://raw.githubusercontent.com/kosinusbch/slp-token-icons/master/128/{token_id}.png"
        status_code, image_file_name = download_image(token_id, url)

    if token_obj.is_nft:
        group = token_obj.nft_token_group

        # Check if NFT group/parent token has image_base_url
        if group and 'image_base_url' in group.nft_token_group_details.keys():
            image_base_url = group.nft_token_group_details['image_base_url']
            image_type = group.nft_token_group_details['image_type']
            url = f"{image_base_url}/{token_id}.{image_type}"
            status_code, image_file_name = download_image(token_id, url, resize=True)

        # Try getting image directly from document URL
        if not image_file_name and is_url(document_url):
            url = document_url
            ipfs_cid = get_ipfs_cid_from_url(url)
            if not ipfs_cid or not url.startswith("ipfs://"):
                status_code, image_file_name = download_image(token_id, url, resize=True)

            # We try from other ipfs gateways if document url is an ipfs link but didnt work
            if not image_file_name and ipfs_cid:
                for ipfs_gateway in ipfs_gateways:
                    url = f"https://{ipfs_gateway}/ipfs/{ipfs_cid}"
                    status_code, image_file_name = download_image(token_id, url, resize=True)
                    if image_file_name:
                        break

        # last fallback, juungle to resolve icon
        # NOTE: juungle is shutting down in March 1, 2023
        if not image_file_name:
            url = f"https://www.juungle.net/api/v1/nfts/icon/{token_id}/{token_id}"
            status_code, image_file_name = download_image(token_id, url, resize=True)

        if status_code == 200 and image_file_name:
            image_url = f"{image_server_base}/{image_file_name}"
            if token_obj.token_type == 1:
                Token.objects.filter(tokenid=token_id).update(
                    original_image_url=image_url,
                    date_updated=timezone.now()
                )
            if token_obj.token_type == 65:
                Token.objects.filter(tokenid=token_id).update(
                    original_image_url=image_url,
                    medium_image_url=image_url.replace(token_id + '.', token_id + '_medium.'),
                    thumbnail_image_url=image_url.replace(token_id + '.', token_id + '_thumbnail.'),
                    date_updated=timezone.now()
                )

    return image_url


@shared_task(bind=True, queue='token_metadata', max_retries=3)
def get_token_meta_data(self, token_id, async_image_download=False):
    try:
        if token_id != settings.WT_DEFAULT_CASHTOKEN_ID:
            t = Token.objects.get(tokenid=token_id)

            LOGGER.info(f'Fetching token metadata from {NODE.SLP.source}...')

            txn = NODE.SLP.get_transaction(token_id, parse_slp=True)
            if not txn:
                return

            info = txn['token_info']
            token_obj_info = dict(
                name = info['name'],
                token_ticker = info['ticker'],
                token_type = info['type'],
                decimals = info['decimals'],
                date_updated = timezone.now(),
                mint_amount = info['mint_amount'] or 0,
            )

            nft_token_group_obj = None
            if info['nft_token_group']:
                nft_token_group_obj, _ = Token.objects.get_or_create(tokenid=info['nft_token_group'])
                token_obj_info["nft_token_group"] = nft_token_group_obj

            token_obj, _ = Token.objects.update_or_create(tokenid=token_id, defaults=token_obj_info)
            if token_obj.token_type in [1, 129]:
                update_token_minting_baton.delay(token_obj.tokenid)

            doc_url = info.get('document_url')

            if async_image_download:
                download_token_metadata_image.delay(token_obj.tokenid, document_url=doc_url)
            else:
                download_token_metadata_image(token_obj.tokenid, document_url=doc_url)

            token_obj.refresh_from_db()
            return token_obj.get_info()
    except Exception as exc:
        LOGGER.error(str(exc))
        self.retry(countdown=5)


@shared_task(queue='token_metadata')
def update_token_minting_baton(tokenid):
    token = Token.objects.filter(tokenid=tokenid).first()
    if not token:
        return { "error": f"token '{tokenid}' not found" }

    if token.token_type not in [1, 129]:
        return { "error": f"invalid token type {token.token_type} for '{tokenid}'"}

    minting_baton = find_minting_baton(tokenid)
    token.save_minting_baton_info(minting_baton)
    return { "tokenid": tokenid, "minting_baton": minting_baton }


@shared_task(queue='wallet_history_1')
def update_nft_owner(tokenid):
    response = { "success": False }

    token = Token.objects.filter(tokenid=tokenid).first()
    if not token or not token.token_type:
        token_info = get_token_meta_data(tokenid, async_image_download=True)
        if token_info:
            token = Token.objects.filter(tokenid=tokenid).first()
        else:
            response["success"] = False
            response["error"] = "token does not exist"
            return response

    if not token.is_nft:
        response["success"] = False
        response["error"] = "token is not an nft type"
        return response

    tx_output = find_token_utxo(token.tokenid)
    if not tx_output:
        response["success"] = False
        response["error"] = "token output not found"
        return response

    wallet = Wallet.objects.filter(addresses__address=tx_output["address"]).first()
    wallet_nft_token = None

    # creating record is conditional since token might be owned by
    # an address that is not subscribed
    if wallet:
        acquisition_tx = Transaction.objects.filter(
            txid=tx_output["txid"],
            index=tx_output["index"],
            address__address=tx_output["address"]
        ).first()

        wallet_nft_token_info = dict(
            wallet=wallet,
            token=token,
            acquisition_transaction=acquisition_tx,
        )
        wallet_nft_token_defaults = dict(date_dispensed=None)
        try:
            wallet_nft_token, _ = WalletNftToken.objects.update_or_create(
                **wallet_nft_token_info,
                defaults=wallet_nft_token_defaults,
            )
        except WalletNftToken.MultipleObjectsReturned:
            WalletNftToken.objects.filter(**wallet_nft_token_info).update(**wallet_nft_token_defaults)

    # marking wallet nft tokens as dispensed will always happen even if wallet is not found 
    to_dispense = WalletNftToken.objects.exclude(
        pk=wallet_nft_token.pk if wallet_nft_token else None,
    ).filter(
        token=token, date_dispensed__isnull=True
    )
    to_dispense.update(date_dispensed=timezone.now())
    dispensed_wallets = list(
        # .order_by() is necessary for .distinct() to function well
        to_dispense.values_list("wallet__wallet_hash", flat=True).distinct().order_by()
    )
    return f"token({token}) | wallet_nft_token: ({wallet_nft_token}) | dispensed: ({dispensed_wallets})"


@shared_task(bind=True, queue='broadcast', max_retries=2)
def broadcast_transaction(self, transaction):
    txid = calc_txid(transaction)
    LOGGER.info(f'Broadcasting {txid}: {transaction}')

    txn_check = Transaction.objects.filter(txid=txid)
    success = False

    if txn_check.exists():
        success = True
        return success, txid
    else:
        try:
            try:
                txid = NODE.BCH.broadcast_transaction(transaction)
                if txid:
                    success = True
                    return success, txid
                else:
                    self.retry(countdown=1)
            except Exception as exc:
                LOGGER.exception(exc)
                error = str(exc)
                return False, error
        except AttributeError as exc:
            LOGGER.exception(exc)
            self.retry(countdown=1)


def process_history_recpts_or_senders(_list, key, BCH_OR_SLP):
    processed_list = []
    if _list:
        processed_list = []
        for _, val in enumerate(_list):
            elem = [
                val[0],
                val[1]
            ]
            if key != BCH_OR_SLP:
                try:
                    cashtoken_data = val[2]
                    if cashtoken_data:
                        elem.append(cashtoken_data['category'])
                        elem.append(cashtoken_data['amount'])

                        if 'nft' in cashtoken_data.keys():
                            nft_data = cashtoken_data['nft']
                            elem.append(nft_data['capability'])
                            elem.append(nft_data['commitment'])
                except IndexError:
                    pass
                
            '''mask remaining fields with None (incurs Django error for non-uniform ArrayField(ArrayField) length for senders/recipients)
            [
                address,
                bch/slp amount,
                ct category/token ID, (can be None)
                ct amount,            (can be None)
                ct capability         (can be None)
                ct commitment         (can be None)
            ]'''
            for x in range(0, 6 - len(elem)):
                elem.append(None)

            processed_list.append(elem)
    return processed_list


@shared_task(bind=True, queue='wallet_history_1')
def parse_wallet_history(self, txid, wallet_handle, tx_fee=None, senders=[], recipients=[], proceed_with_zero_amount=False):
    wallet_hash = wallet_handle.split('|')[1]
    parser = HistoryParser(txid, wallet_hash)
    parsed_history = parser.parse()

    wallet = Wallet.objects.get(wallet_hash=wallet_hash)

    if type(tx_fee) is str:
        tx_fee = float(tx_fee)
    
    BCH_OR_SLP = 'bch_or_slp'

    for key in parsed_history.keys():
        data = parsed_history[key]
        record_type = data['record_type']
        amount = data['diff']
        change_address = data['change_address']

        if wallet.wallet_type == 'bch':
            # Correct the amount for outgoing, subtract the miner fee if given and maintain negative sign
            if record_type == 'outgoing':
                if key == BCH_OR_SLP:
                    amount = abs(amount) - ((tx_fee / 100000000) or 0)
                    amount = round(amount, 8)
                amount = abs(amount) * -1

            # Don't save a record if resulting amount is zero or dust
            is_zero_amount = amount == 0 or amount == abs(0.00000546)
            if is_zero_amount and not proceed_with_zero_amount:
                return

            if is_zero_amount:
                record_type = ''

            bch_prefix = 'bitcoincash:'
            if settings.BCH_NETWORK != 'mainnet':
                bch_prefix = 'bchtest:'

            txns = Transaction.objects.filter(
                txid=txid,
                address__address__startswith=bch_prefix
            )
            if key == BCH_OR_SLP:
                txns = txns.filter(token__name='bch')
            else:
                txns = txns.exclude(token__name='bch')

        elif wallet.wallet_type == 'slp':
            if key != BCH_OR_SLP:
                return

            txns = Transaction.objects.filter(
                txid=txid,
                address__address__startswith='simpleledger:'
            )

        txn = txns.last()
        tx_timestamp = txns.filter(tx_timestamp__isnull=False).aggregate(_max=models.Max('tx_timestamp'))['_max']

        if not txn: continue

        if change_address:
            recipients = [(info[0], info[1]) for info in recipients if info[0] != change_address]

        processed_recipients = process_history_recpts_or_senders(recipients, key, BCH_OR_SLP)
        processed_senders = process_history_recpts_or_senders(senders, key, BCH_OR_SLP)

        history_check = WalletHistory.objects.filter(
            wallet=wallet,
            txid=txid,
            token=txn.token,
            cashtoken_ft=txn.cashtoken_ft,
            cashtoken_nft=txn.cashtoken_nft
        )
        if history_check.exists():
            history_check.update(
                record_type=record_type,
                amount=amount,
                token=txn.token,
                cashtoken_ft=txn.cashtoken_ft,
                cashtoken_nft=txn.cashtoken_nft
            )
            if tx_fee and processed_senders and processed_recipients:
                history_check.update(
                    tx_fee=tx_fee,
                    senders=processed_senders,
                    recipients=processed_recipients
                )
            if tx_timestamp:
                history_check.update(
                    tx_timestamp=tx_timestamp,
                )
                resolve_wallet_history_usd_values.delay(txid=txid)
                for history in history_check:
                    parse_wallet_history_market_values.delay(history.id)
        else:
            history = WalletHistory(
                wallet=wallet,
                txid=txid,
                record_type=record_type,
                amount=amount,
                token=txn.token,
                cashtoken_ft=txn.cashtoken_ft,
                cashtoken_nft=txn.cashtoken_nft,
                tx_fee=tx_fee,
                senders=processed_senders,
                recipients=processed_recipients,
                date_created=txn.date_created,
                tx_timestamp=tx_timestamp,
            )
            history.save()

            resolve_wallet_history_usd_values.delay(txid=txid)

            if history.tx_timestamp:
                try:
                    parse_wallet_history_market_values(history.id)
                    history.refresh_from_db()
                except Exception:
                    LOGGER.exception(exception)

            try:
                # Do not send notifications for amounts less than or equal to 0.00001
                if abs(amount) > 0.00001:
                    LOGGER.info(f"PUSH_NOTIF: wallet_history for #{history.txid} | {history.amount}")
                    send_wallet_history_push_notification(history)
            except Exception as exception:
                LOGGER.exception(exception)

        # for older token records 
        if (
            txn.token and
            txn.token.tokenid and
            txn.token.tokenid != settings.WT_DEFAULT_CASHTOKEN_ID and
            (txn.token.token_type is None or txn.token.mint_amount is None)
        ):
            get_token_meta_data(txn.token.tokenid, async_image_download=True)
            txn.token.refresh_from_db()

        if txn.token and txn.token.is_nft:
            if record_type == 'incoming':
                wallet_nft_token, created = WalletNftToken.objects.get_or_create(
                    wallet=wallet,
                    token=txn.token,
                    acquisition_transaction=txn
                )
            elif record_type == 'outgoing':
                wallet_nft_token_check = WalletNftToken.objects.filter(
                    wallet=wallet,
                    token=txn.token,
                    date_dispensed__isnull=True
                )
                if wallet_nft_token_check.exists():
                    wallet_nft_token = wallet_nft_token_check.last()
                    wallet_nft_token.date_dispensed = txn.date_created
                    wallet_nft_token.dispensation_transaction = txn
                    wallet_nft_token.save()

            update_nft_owner.delay(txn.token.tokenid)

@shared_task(queue='client_acknowledgement')
def send_wallet_history_push_notification_task(wallet_history_id):
    LOGGER.info(f"PUSH_NOTIF: wallet_history:{wallet_history_id}")
    history = WalletHistory.objects.get(id=wallet_history_id)
    try:
        if not history.fiat_value:
            try:
                parse_wallet_history_market_values(history.id)
                history.refresh_from_db()
            except Exception as exception:
                LOGGER.exception(exception)
        # Do not send notifications for amounts less than or equal to 0.00001
        if abs(history.amount) > 0.00001:
            LOGGER.info(f"PUSH_NOTIF CURRENCY: wallet_history:{history.txid} | {history.amount} | {history.fiat_value} | {history.usd_value} | {history.market_prices}")
            return send_wallet_history_push_notification(history)
    except Exception as exception:
        LOGGER.exception(exception)


@shared_task(bind=True, queue='post_save_record', max_retries=10)
def transaction_post_save_task(self, address, transaction_id, blockheight_id=None):
    txid = Transaction.objects.values_list("txid", flat=True).filter(id=transaction_id).first()
    if not txid: return

    LOGGER.info(f"TX POST SAVE TASK: {address} | {txid} | {blockheight_id}")

    if not BlockHeight.objects.filter(id=blockheight_id).exists():
        blockheight_id = None

    wallets = []
    txn_address = Address.objects.get(address=address)
    wallet_type = None
    wallet_hash = None
    if txn_address.wallet:
        wallet_type = txn_address.wallet.wallet_type
        wallet_hash = txn_address.wallet.wallet_hash
        wallets.append(wallet_type + '|' + wallet_hash)

    parse_slp = is_slp_address(address)
    bch_tx = NODE.BCH.get_transaction(txid)
    slp_tx = None
    if parse_slp:
        slp_tx = NODE.SLP.get_transaction(txid, parse_slp=True)

    if parse_slp and not isinstance(slp_tx, dict) and not slp_tx.get('valid'):
        self.retry(countdown=5)
        return

    if not bch_tx:
        self.retry(countdown=5)
        return

    tx_timestamp = bch_tx['timestamp']
    # use batch update to not trigger the post save signal and potentially create an infinite loop
    parsed_tx_timestamp = datetime.fromtimestamp(tx_timestamp).replace(tzinfo=pytz.UTC)
    Transaction.objects.filter(txid=txid, tx_timestamp__isnull=True).update(tx_timestamp=parsed_tx_timestamp)

    # Extract tx_fee, senders, and recipients
    tx_fee = bch_tx['tx_fee']
    senders = { 'bch': [], 'slp': [] }
    recipients = { 'bch': [], 'slp': [] }

    # Parse SLP senders and recipients
    if parse_slp and wallet_type == 'slp':
        senders['slp'] = [parse_utxo_to_tuple(i, is_slp=True) for i in slp_tx['inputs']]
        if 'outputs' in slp_tx:
            recipients['slp'] = [parse_utxo_to_tuple(i, is_slp=True) for i in slp_tx['outputs']]

    # Parse BCH senders and recipients
    if wallet_type == 'bch':
        senders['bch'] = [parse_utxo_to_tuple(i) for i in bch_tx['inputs']]
        if 'outputs' in bch_tx:
            recipients['bch'] = [parse_utxo_to_tuple(i)for i in bch_tx['outputs']]

    # Resolve wallets
    addresses = [*bch_tx['inputs'], *bch_tx['outputs']]
    if parse_slp: addresses += [*slp_tx['inputs'], *slp_tx['outputs']]
    addresses = [i['address'] for i in addresses]

    wallets += Address.objects \
        .filter(address__in=addresses, wallet__isnull=False) \
        .filter(wallet__wallet_type__in=['slp', 'bch']) \
        .annotate(wallet_handle=models.functions.Concat(
            models.F('wallet__wallet_type'),
            models.Value('|'),
            models.F('wallet__wallet_hash'),
        )) \
        .values_list('wallet_handle', flat=True)

    if parse_slp:
        # Mark SLP tx inputs as spent
        for tx_input in slp_tx['inputs']:
            txn_check = Transaction.objects.filter(
                txid=tx_input['txid'],
                index=tx_input['spent_index'],
            )

            if not txn_check.exists(): continue
            txn_check.update(spent=True, spending_txid=txid)

            txn_obj = txn_check.last()
            if txn_obj.token.is_nft:
                wallet_nft_tokens = WalletNftToken.objects.filter(acquisition_transaction=txn_obj)
                if wallet_nft_tokens.exists():
                    wallet_nft_tokens.update(
                        date_dispensed = timezone.now(),
                        dispensation_transaction = transaction,
                    )

        # Parse SLP tx outputs
        for tx_output in slp_tx['outputs']:
            txn_check = Transaction.objects.filter(
                txid=slp_tx['txid'],
                address__address=tx_output['address'],
                index=tx_output['index']
            )
            if not txn_check.exists():
                obj_id, created = save_record(
                    slp_tx['token_id'],
                    tx_output['address'],
                    slp_tx['txid'],
                    NODE.SLP.source,
                    amount=tx_output['amount'],
                    blockheightid=blockheight_id,
                    index=tx_output['index'],
                    tx_timestamp=tx_timestamp
                )

                if created:
                    client_acknowledgement(obj_id)

    # Mark BCH tx inputs as spent
    for tx_input in bch_tx['inputs']:
        txn_check = Transaction.objects.filter(
            txid=tx_input['txid'],
            index=tx_input['spent_index'],
        )

        if not txn_check.exists(): continue
        txn_check.update(spent=True, spending_txid=txid)

    # Parse BCH tx outputs
    for tx_output in bch_tx['outputs']:
        txn_check = Transaction.objects.filter(
            txid=bch_tx['txid'],
            address__address=tx_output['address'],
            index=tx_output['index']
        )

        if not txn_check.exists():
            if tx_output['token_data']:
                process_cashtoken_tx(
                    tx_output['token_data'],
                    tx_output['address'],
                    bch_tx['txid'],
                    block_id=blockheight_id,
                    index=tx_output['index'],
                    timestamp=bch_tx['timestamp'],
                    value=tx_output['value']
                )
            else:
                value = tx_output['value'] / 10 ** 8
                obj_id, created = save_record(
                    'bch',
                    tx_output['address'],
                    bch_tx['txid'],
                    NODE.BCH.source,
                    value=value,
                    blockheightid=blockheight_id,
                    index=tx_output['index'],
                    tx_timestamp=bch_tx['timestamp']
                )
                if created:
                    client_acknowledgement(obj_id)

    # Call task to parse wallet history
    for wallet_handle in set(wallets):
        if wallet_handle.split('|')[0] == 'slp':
            if senders['slp'] and recipients['slp']:
                parse_wallet_history.delay(
                    txid,
                    wallet_handle,
                    tx_fee,
                    senders['slp'],
                    recipients['slp']
                )
        if wallet_handle.split('|')[0] == 'bch':
            if senders['bch'] and recipients['bch']:
                parse_wallet_history.delay(
                    txid,
                    wallet_handle,
                    tx_fee,
                    senders['bch'],
                    recipients['bch']
                )

    return list(set(wallets))


@shared_task(queue='rescan_utxos')
def rescan_utxos(wallet_hash, full=False):
    wallet = Wallet.objects.get(wallet_hash=wallet_hash)
    if full:
        addresses = wallet.addresses.all()
    else:
        addresses = wallet.addresses.filter(transactions__spent=False)

    for address in addresses:
        if wallet.wallet_type == 'bch':
            get_bch_utxos(address.address)
        elif wallet.wallet_type == 'slp':
            get_slp_utxos(address.address)


@shared_task(queue='wallet_history_1', max_retries=3)
def parse_tx_wallet_histories(txid, proceed_with_zero_amount=False, immediate=False):
    LOGGER.info(f"PARSE TX WALLET HISTORIES: {txid}")

    bch_tx = NODE.BCH.get_transaction(txid)

    tx_fee = bch_tx['tx_fee']
    tx_timestamp = bch_tx['timestamp']

    # parse inputs and outputs to desired structure
    inputs = [parse_utxo_to_tuple(i) for i in bch_tx['inputs']]
    outputs = [parse_utxo_to_tuple(i) for i in bch_tx['outputs']]

    # get bch wallets with addresses that are in inputs and outputs
    input_addresses = [i[0] for i in inputs]
    output_addresses = [i[0] for i in outputs]
    addresses = set([*input_addresses, *output_addresses])
    wallets = Wallet.objects.filter(addresses__address__in=addresses, wallet_type="bch")
    wallet_hashes = wallets.values_list("wallet_hash", flat=True)

    utxos = extract_tx_utxos(bch_tx)
    has_saved_output = Transaction.objects.filter(txid=txid).exists()
    for i, utxo in enumerate(utxos):
        is_output = not utxo['is_input']

        force_create = False
        if i == len(utxos)-1 and not has_saved_output: force_create = True

        if not force_create:
            txn_check = Transaction.objects.filter(txid=utxo['txid'], index=utxo['index'])
            if txn_check.exists():
                txn_check.update(spent=True, spending_txid=txid)
                continue

            inp_wallet_hash = Address.objects.filter(address=utxo['address']).values_list("wallet__wallet_hash", flat=True).first()
            if inp_wallet_hash not in wallet_hashes:
                continue

        if is_output: has_saved_output = True

        if utxo['token_data']:
            process_cashtoken_tx(
                utxo['token_data'],
                utxo['address'],
                utxo['txid'],
                index=utxo['index'],
                timestamp=tx_timestamp if is_output else None,
                force_create=force_create,
                value=utxo['value'],
            )
        else:
            save_record(
                'bch',
                utxo['address'],
                utxo['txid'],
                NODE.BCH.source,
                value=utxo['value'],
                index=utxo['index'],
                tx_timestamp=tx_timestamp if is_output else None,
                force_create=force_create,
            )

        if not is_output:
            Transaction.objects \
                .filter(txid=utxo['txid'], index=utxo['index']) \
                .update(spent=True, spending_txid=txid)

        tx_obj = Transaction.objects \
            .filter(txid=utxo['txid'], index=utxo['index']) \
            .annotate(
                addr=models.F("address__address"),
                wallet_hash=models.F("wallet__wallet_hash"),
                token_name=models.F("token__name"),
            ) \
            .first()

    # parse wallet history of bch wallets
    wallet_handles = []
    for wallet in wallets:
        wallet_handle = f"bch|{wallet.wallet_hash}"
        wallet_handles.append(wallet_handle)
        if immediate:
            parse_wallet_history(
                txid,
                wallet_handle,
                tx_fee,
                inputs,
                outputs,
                proceed_with_zero_amount=proceed_with_zero_amount,
            )
        else:
            parse_wallet_history.delay(
                txid,
                wallet_handle,
                tx_fee,
                inputs,
                outputs,
                proceed_with_zero_amount=proceed_with_zero_amount,
            )

    return wallet_handles


@shared_task(queue='wallet_history_2', max_retries=3)
def find_wallet_history_missing_tx_timestamps():
    NO_TXIDS_TO_PARSE = 15
    txids = WalletHistory.objects.filter(
        tx_timestamp__isnull=True,
    ).order_by('-date_created').values_list('txid', flat=True).distinct()[:NO_TXIDS_TO_PARSE]

    # get transactions from 
    tx_timestamps = Transaction.objects.filter(
        txid__in=txids,
        tx_timestamp__isnull=False
    ).values('txid', 'tx_timestamp').union(
        WalletHistory.objects.filter(
            txid__in=txids,
            tx_timestamp__isnull=False,
        ).values('txid', 'tx_timestamp')
    ).distinct()
    tx_timestamps_map = {tx['txid']: tx['tx_timestamp'] for tx in tx_timestamps}

    txids_updated = []
    for txid in txids:
        _tx_timestamp = tx_timestamps_map.get(txid)
        if not _tx_timestamp:
            tx = NODE.BCH.get_transaction(txid)
            _tx_timestamp = tx["timestamp"] if tx else None
        if not _tx_timestamp:
            continue
        try:
            tx_timestamp = datetime.fromtimestamp(_tx_timestamp).replace(tzinfo=pytz.UTC)
        except TypeError:
            tx_timestamp = _tx_timestamp.replace(tzinfo=pytz.UTC)
        WalletHistory.objects.filter(txid=txid).update(tx_timestamp=tx_timestamp)
        Transaction.objects.filter(txid=txid).update(tx_timestamp=tx_timestamp)
        txids_updated.append([txid, _tx_timestamp])
    return txids_updated


@shared_task(queue='wallet_history_2', max_retries=3)
def resolve_wallet_history_usd_values(txid=None):
    CURRENCY = "USD"
    RELATIVE_CURRENCY = "BCH"
    queryset = WalletHistory.objects.filter(
        token__name="bch",
        usd_price__isnull=True,
        tx_timestamp__isnull=False,
    )
    if txid:
        queryset = queryset.filter(txid = txid)

    timestamps = queryset.order_by(
        "-tx_timestamp",
    ).values_list('tx_timestamp', flat=True).distinct()[:15]

    txids_updated = []
    for timestamp in timestamps:
        price_value_data = fetch_currency_value_for_timestamp(timestamp, currency=CURRENCY, relative_currency=RELATIVE_CURRENCY)
        if not price_value_data:
            continue

        (price_value, actual_timestamp, price_data_source) = price_value_data
        wallet_histories = WalletHistory.objects.filter(
            token__name="bch",
            tx_timestamp=timestamp,
        )
        wallet_histories.update(usd_price=price_value)
        txids = list(wallet_histories.values_list("txid", flat=True).distinct())
        txids_updated = txids_updated + txids

        price_log_data = {
            'currency': CURRENCY,
            'relative_currency': RELATIVE_CURRENCY,
            'timestamp': actual_timestamp,
            'source': price_data_source
        }
        price_log_check = AssetPriceLog.objects.filter(**price_log_data)
        if price_log_check.exists():
            price_log = price_log_check.first()
            price_log.price_value = price_value
            price_log.save()
        else:
            price_log_data['price_value'] = price_value
            price_log = AssetPriceLog(**price_log_data)
            price_log.save()

    return txids_updated

@shared_task(queue='wallet_history_2', max_retries=3)
def fetch_latest_usd_price():
    CURRENCY = "USD"
    RELATIVE_CURRENCY = "BCH"
    to_timestamp = timezone.now()
    from_timestamp = to_timestamp - timezone.timedelta(minutes=10)
    coingecko_resp = requests.get(
        "https://api.coingecko.com/api/v3/coins/bitcoin-cash/market_chart/range?" + \
        f"vs_currency={CURRENCY}" + \
        f"&from={from_timestamp.timestamp()}" + \
        f"&to={to_timestamp.timestamp()}"
    )

    coingecko_prices_list = None
    try:
        response_data = coingecko_resp.json()
        if isinstance(response_data, dict) and "prices" in response_data:
            coingecko_prices_list = response_data.get("prices", [])
    except json.decoder.JSONDecodeError:
        pass

    asset_prices = []
    for coingecko_price_data in coingecko_prices_list:
        timestamp = coingecko_price_data[0]/1000
        timestamp_obj = timezone.datetime.fromtimestamp(timestamp).replace(tzinfo=pytz.UTC)
        price_value = Decimal(coingecko_price_data[1])
        instance, created = AssetPriceLog.objects.update_or_create(
            currency=CURRENCY,
            relative_currency=RELATIVE_CURRENCY,
            timestamp=timestamp_obj,
            source="coingecko",
            defaults={ "price_value": price_value }
        )
        asset_prices.append({
            "currency": instance.currency,
            "timestamp": instance.timestamp,
            "source": instance.source,
            "price_value": instance.price_value,
        })

    return asset_prices

@shared_task(queue='wallet_history_2', max_retries=3)
def parse_wallet_history_market_values(wallet_history_id):
    if not wallet_history_id:
        return
    try:
        wallet_history_obj = WalletHistory.objects.get(id=wallet_history_id)
    except WalletHistory.DoesNotExist:
        return

    if wallet_history_obj.tx_timestamp is None:
        return

    # block for bch txs only
    if wallet_history_obj.token.name != "bch":
        return

    LOGGER.info(" | ".join([
        f"WALLET_HISTORY_MARKET_VALUES",
        f"{wallet_history_obj.id}:{wallet_history_obj.txid}",
        f"{wallet_history_obj.tx_timestamp}",
    ]))

    # resolves the currencies needed to store for the wallet history
    currencies = []
    try:
        if wallet_history_obj.wallet and wallet_history_obj.wallet.preferences and wallet_history_obj.wallet.preferences.selected_currency:
            currencies.append(wallet_history_obj.wallet.preferences.selected_currency)
    except Wallet.preferences.RelatedObjectDoesNotExist:
        pass

    currencies = [c.upper() for c in currencies if isinstance(c, str) and len(c)]

    market_prices = wallet_history_obj.market_prices or {}
    if wallet_history_obj.usd_price:
        market_prices["USD"] = wallet_history_obj.usd_price

    # check for existing price logs that can be used
    timestamp = wallet_history_obj.tx_timestamp
    timestamp_range_low = timestamp - timezone.timedelta(seconds=30)
    timestamp_range_high = timestamp + timezone.timedelta(seconds=30)
    asset_price_logs = AssetPriceLog.objects.filter(
        currency__in=currencies,
        relative_currency="BCH",
        timestamp__gt = timestamp_range_low,
        timestamp__lt = timestamp_range_high,
    ).annotate(
        diff=models.Func(models.F("timestamp"), timestamp, function="GREATEST") - models.Func(models.F("timestamp"), timestamp, function="LEAST")
    ).order_by("-diff")

    # sorting above is closest timestamp last so the loop below ends up with the closest one
    for price_log in asset_price_logs:
        market_prices[price_log.currency] = price_log.price_value

    # last resort for resolving prices, only for new txs
    missing_currencies = [c for c in currencies if c not in market_prices]
    tx_age = (timezone.now() - timestamp).total_seconds()
    if tx_age < 30 and len(missing_currencies):
        bch_rates = get_latest_bch_rates(currencies=missing_currencies)
        for currency in missing_currencies:
            bch_rate = bch_rates.get(currency.lower(), None)
            if bch_rate:
                market_prices[currency] = bch_rate[0]

                price_log_data = {
                    'currency': currency,
                    'relative_currency': "BCH",
                    'timestamp': bch_rate[1],
                    'source': bch_rate[2]
                }
                price_log_check = AssetPriceLog.objects.filter(**price_log_data)
                if price_log_check.exists():
                    price_log = price_log_check.first()
                    price_log.price_value = bch_rate[0]
                    price_log.save()
                else:
                    price_log_data['price_value'] = bch_rate[0]
                    price_log = AssetPriceLog(**price_log_data)
                    price_log.save()

    wallet_history_obj.market_prices = market_prices
    if "USD" in wallet_history_obj.market_prices and not wallet_history_obj.usd_price:
        wallet_history_obj.usd_price = wallet_history_obj.market_prices["USD"]
    for currency, price in wallet_history_obj.market_prices.items():
        if isinstance(price, Decimal):
            wallet_history_obj.market_prices[currency] = float(price)
    wallet_history_obj.save()
    return {
        "id": wallet_history_obj.id,
        "txid": wallet_history_obj.txid,
        "tx_timestamp": str(wallet_history_obj.tx_timestamp),
        "market_prices": market_prices,
        "TX_AGE": tx_age,
    }


@shared_task(queue='wallet_history_2', max_retries=3)
def update_wallet_history_currency(wallet_hash, currency):
    return save_wallet_history_currency(wallet_hash, currency)


@shared_task(queue='populate_token_addresses')
def populate_token_addresses():
    bch_addresses = Address.objects.filter(
        models.Q(address__startswith='bitcoincash:') |
        models.Q(address__startswith='bchtest:')
    ).filter(
        token_address__isnull=True
    ).order_by('id')

    for obj in bch_addresses:
        if is_bch_address(obj.address): # double check here
            obj.token_address = bch_address_converter(obj.address)
            obj.save()
