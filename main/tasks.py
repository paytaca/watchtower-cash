import logging, json, requests
import pytz, time
import math
from decimal import Decimal
from datetime import datetime
from urllib.parse import urlparse
from django.db import models
from watchtower.settings import MAX_RESTB_RETRIES
from celery import shared_task
from celery_heimdall import HeimdallTask, RateLimit
from main.mqtt import publish_message
from watchtower.celery import app as celery_app
from main.models import *
from main.utils.address_validator import *
from paytacapos.models import Merchant, PosDevice
from main.utils.ipfs import (
    get_ipfs_cid_from_url,
    ipfs_gateways,
)
from main.utils.logging import get_stack_frames, format_stack_frame
from main.utils.market_price import (
    fetch_currency_value_for_timestamp,
    get_latest_bch_rates,
    get_and_save_latest_bch_rates,
    save_wallet_history_currency,
    CoingeckoAPI,
    get_ft_bch_price_log,
)
from celery.exceptions import MaxRetriesExceededError 
from main.utils.nft import (
    find_token_utxo,
    find_minting_baton,
)
from main.utils.address_converter import bch_address_converter
from main.utils.address_scan import get_bch_transactions
from main.utils.address_validator import is_bch_address
from main.utils.wallet import HistoryParser
from main.utils.push_notification import (
    send_wallet_history_push_notification,
    send_wallet_history_push_notification_nft
)
from django.db.utils import IntegrityError
from django.conf import settings
from django.utils import timezone, dateparse
from django.db import transaction as trans
from celery.exceptions import TimeoutError
from main.utils.chunk import chunks
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from main.utils.queries.node import Node
from main.utils.queries.parse_utils import (
    parse_utxo_to_tuple,
    extract_tx_utxos,
    flatten_output_data,
)
from Crypto.Hash import SHA256  # pycryptodome
import paho.mqtt.client as mqtt
from PIL import Image, ImageFile
from io import BytesIO 
import pytz

import rampp2p.utils.transaction as rampp2p_utils
from jpp.models import Invoice as JPPInvoice
from main.utils.transaction_processing import mark_transaction_inputs_as_spent, mark_transactions_as_spent


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
def client_acknowledgement(self, tx_obj_id):
    stack_frames = get_stack_frames(1, 5)
    trigger_info = "\n".join([format_stack_frame(frame) for frame in stack_frames])
    LOGGER.info(f"Client ACK: Transaction#{tx_obj_id}. Triggered from {trigger_info}")

    this_transaction = Transaction.objects.filter(id=tx_obj_id)
    if this_transaction.exists():
        transaction = this_transaction.first()
        block = None
        if transaction.blockheight:
            block = transaction.blockheight.number

        jpp_invoice_uuid = JPPInvoice.objects \
            .filter(payment__txid=transaction.txid) \
            .values_list("uuid", flat=True) \
            .first()
        address = transaction.address

        subscriptions = Subscription.objects.filter(address=address)
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
                category = None

                # note that transaction can have cashtoken_ft & cashtoken_nft
                # cashtoken_nft is used if there is both
                if transaction.cashtoken_ft:
                    token = transaction.cashtoken_ft
                    token_details_key = 'fungible'
                if transaction.cashtoken_nft:
                    token = transaction.cashtoken_nft
                    token_details_key = 'nft'
                    category = token.token_id.split('/')[1]

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
                    }

                    if transaction.cashtoken_nft:
                        data['capability'] = token.capability
                        data['commitment'] = token.commitment
                        data['id'] = token.id
                        data['is_nft'] = True

                    if jpp_invoice_uuid:
                        data['jpp_invoice_uuid'] = jpp_invoice_uuid

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
                            elif resp.status_code == 400:
                                Recipient.objects.filter(id=recipient.id).update(valid=False)
                                LOGGER.info(f"!!! ATTENTION !!! ENCOUNTERED AN ERROR SENDING REQUEST TO: {recipient.web_url}")
                            else:
                                LOGGER.error(resp)
                                self.retry(countdown=3)

                            this_transaction.update(acknowledged=True)

                if websocket:
                    tokenid = transaction.token.tokenid
                    room_name = transaction.address.address.replace(':','_')

                    if tokenid == settings.WT_DEFAULT_CASHTOKEN_ID:
                        tokenid = ''

                    room_name += f'_{tokenid}'

                    channel_layer = get_channel_layer()
                    async_to_sync(channel_layer.group_send)(
                        f"{room_name}", 
                        {
                            "type": "send_update",
                            "data": data
                        }
                    )

                    if address.wallet:
                        channel_layer = get_channel_layer()
                        async_to_sync(channel_layer.group_send)(
                            f"{address.wallet.wallet_hash}", 
                            {
                                "type": "send_update",
                                "data": data
                            }
                        )


def get_cashtoken_meta_data(
    category,
    txid=None,
    index=None,
    is_nft=False,
    nft_has_fungible=False, # some cashtokens are both ft & nft
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
        # Truncate all string fields to safe lengths
        name = (METADATA['name'] or default_details['name'])[:200]  # Safe limit for name
        description = METADATA['description'][:1000] if METADATA['description'] else ''  # Reasonable limit for description
        symbol = (METADATA['symbol'] or default_details['symbol'])[:100]  # Model limit for symbol
        decimals = METADATA['decimals']
        image_url = METADATA['uris']['icon'][:200] if METADATA['uris'].get('icon') else None  # Safe limit for URL
        
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
                            name = nfts['name'][:200]  # Safe limit for name
                        if 'description' in nft_keys:
                            description = nfts['description'][:1000] if nfts['description'] else ''  # Reasonable limit for description
                        if 'uris' in nft_keys:
                            uris = nfts['uris']
                            if 'icon' in uris.keys():
                                image_url = uris['icon'][:200] if uris['icon'] else None  # Safe limit for URL
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
        name = default_details['name'][:200]  # Safe limit for name
        symbol = default_details['symbol'][:100]  # Model limit for symbol
            
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
        resolve_ct_nft_genesis(cashtoken, txid=txid)

    if not is_nft or nft_has_fungible:
        _cashtoken, _ = CashFungibleToken.objects.get_or_create(category=category)
        _cashtoken.fetch_metadata()

        if not is_nft: cashtoken = _cashtoken

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

    stack_frames = get_stack_frames(1, 5)
    trigger_info = "\n\t >> ".join([format_stack_frame(frame) for frame in stack_frames])
    LOGGER.info(f'Saving txid: {transactionid} | #{index} | {transaction_address}\nTriggered from {trigger_info}')
    rampp2p_utils.process_transaction(transactionid, transaction_address, inputs=inputs)

    address_obj, _ = Address.objects.get_or_create(address=transaction_address)

    try:
        index = int(index)
    except TypeError as exc:
        index = 0

    with trans.atomic():
        transaction_created = False
        cashtoken = None
        ct_nft_hash_fungible = bool(is_cashtoken_nft and amount)

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
                    is_nft=is_cashtoken_nft,
                    nft_has_fungible=ct_nft_hash_fungible,
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
                if not is_cashtoken_nft or ct_nft_hash_fungible:
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
                    value=tx_input["value"],
                    index=tx_input["outpoint_index"],
                    spending_txid=transaction_obj.txid,
                    force_create=True
                )
        return transaction_obj.id, transaction_created


def process_output(
    output_data,
    txid,
    block_id=None,
    timestamp=None,
    source=None,
    force_create=False,
    inputs=None,
    send_client_acknowledgement=True
):
    """
    Process a single transaction output (BCH or CashToken).
        Created to keep DRY principle. Found functions processs_cashtoken_tx, save_record, & send_client_acknowledgement
        keep getting called in the same pattern multiple times.
    Args:
        output_data: See BCHN._parse_output() for expected structure
        txid: Transaction ID (required)
        block_id: Block height ID (optional)
        timestamp: Transaction timestamp (optional)
        source: Transaction source (defaults to NODE.BCH.source)
        force_create: Force create transaction even if not subscribed (default: False)
        inputs: Input data for save_record (optional)
        send_client_acknowledgement: Whether to call client_acknowledgement if created (default: True)
    """
    created = False
    # Extract required fields from output_data
    (index, address, value, category, amount, capability, commitment) = flatten_output_data(output_data)
    is_cashtoken = bool(category)
    is_cashtoken_nft = bool(category and capability)

    if not address:
        # Handle op_return or script outputs (no address)
        # These typically don't need to be saved as transactions
        return {
            'transaction_id': None,
            'created': False,
            'token_id': 'bch',
            'decimals': None,
            'amount': '',
            'value': value
        }

    # Default source
    if source is None:
        source = NODE.BCH.source

    tokenid = 'bch'
    return_tokenid = 'bch'
    if category:
        tokenid = category
        return_tokenid = 'ct/' + category

    obj_id, created = save_record(
        tokenid,
        address,
        txid,
        source,
        amount=amount,
        value=value,
        blockheightid=block_id,
        tx_timestamp=timestamp,
        index=index,
        is_cashtoken=is_cashtoken,
        is_cashtoken_nft=is_cashtoken_nft,
        capability=capability,
        commitment=commitment,
        force_create=force_create,
        inputs=inputs,
    )

    # Send client acknowledgement if requested and transaction was created
    if created and send_client_acknowledgement:
        client_acknowledgement(obj_id)

    # not sure why decimals should only be provided if created,
    # but keeping it this way to keep logic during refactor
    decimals = None
    if created:
        txn_obj = Transaction.objects.get(id=obj_id)
        decimals = txn_obj.get_token_decimals()
    
    return {
        'transaction_id': obj_id,
        'created': created,
        'token_id': return_tokenid,
        'decimals': decimals,
        'amount': amount or '',
        'value': value
    }

def resolve_ct_nft_genesis(cashtoken:CashNonFungibleToken, txid=""):
    """
        Determines whether a CashToken NFT is from a fixed supply or not
        Will attempt to save a minting NFT transaction if not fixed supply
    """
    if not isinstance(cashtoken, CashNonFungibleToken):
        return

    minting_nft = None
    if cashtoken.capability == "minting":
        minting_nft = cashtoken
    elif cashtoken.fixed_supply is None:
        minting_nft = CashNonFungibleToken.objects.filter(
            category=cashtoken.category, capability="minting"
        ).first()

    if minting_nft:
        cashtoken.fixed_supply = False

    elif cashtoken.fixed_supply is None or not minting_nft:
        try:
            cashtoken.fixed_supply = find_and_save_minting_transaction(
                txid=txid,
                category=cashtoken.category,
                capability=cashtoken.capability,
                commitment=cashtoken.commitment,
            )
        except Exception as exc:
            LOGGER.error(f"Error in finding and saving minting transaction: {exc}")
            LOGGER.exception(exc)

    cashtoken.save()
    return cashtoken

@shared_task(queue='query_transaction')
def find_and_save_minting_transaction(txid="", category="", capability="", commitment="", max_depth=20):
    """
        Traces back to the minting transaction of a CashToken NFT and save the minting nft's transaction
        Returns null if no genesis transaction found
        Returns True if NFT is not created from a minting NFT, otherwise False
    """
    try:
        result = get_ct_nft_genesis_tx(
            txid=txid,
            category=category,
            capability=capability,
            commitment=commitment,
            max_depth=max_depth,
        )
    except StopIteration as exception:
        LOGGER.error(exception)
        return

    if not result: return

    if not result["is_nft"]:
        return True

    save_minting_nft_transaction(result["transaction"], result["minting_input_index"])
    return False


def get_ct_nft_genesis_tx(txid="", category="", capability="", commitment="", max_depth=20):
    if max_depth == 0:
        raise StopIteration("Max depth reached")

    tx = NODE.BCH.get_transaction(txid)
    token_data = {
        "category": category,
        "nft": { "capability": capability, "commitment": commitment },
    }
    LOGGER.debug("CT NFT GENESIS SEARCH | txid:", txid, "depth:", max_depth, "token_data:", token_data)
    for index, tx_input in enumerate(tx["inputs"]):
        if category == tx_input["txid"]:
            return dict(transaction=tx, minting_input_index=index, is_nft=False)

        if not tx_input.get("token_data"): continue
        if "category" not in tx_input["token_data"]: continue
        if "nft" not in tx_input["token_data"]: continue

        token_data = tx_input["token_data"]
        if token_data["nft"]["capability"] == "minting":
            return dict(transaction=tx, minting_input_index=index, is_nft=True)

        if category == token_data["category"] and \
            capability == token_data["nft"]["capability"] and \
            commitment == token_data["nft"]["commitment"]:

            return get_ct_nft_genesis_tx(
                txid=tx_input["txid"],
                category=category,
                capability=capability,
                commitment=commitment,
                max_depth=max_depth-1,
            )

def save_minting_nft_transaction(transaction:dict, minting_input_index:int):
    minting_input = transaction["inputs"][minting_input_index]

    if minting_input.get("token_data"): return
    if "nft" not in minting_input["token_data"]: return
    if "capability" not in minting_input["token_data"]["nft"]: return
    if minting_input["token_data"]["nft"]["capability"] != "minting": return

    # minting_input seems to have similar structure as
    # expected output_data when inspected during refactor
    minting_input_as_output_data = { **minting_input, "index": minting_input["spent_index"] }
    process_output(
        minting_input_as_output_data,
        minting_input["txid"], force_create=True,
    )

    # using this method of update to skip triggering post save signals
    # process_output will probably fire it already
    Transaction.objects.filter(id=process_result["transaction_id"]).update(
        spending_txid=transaction["txid"],
        spent=True,
    )
    return process_result


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
                parsed_output = NODE.BCH._parse_output(output)

                process_output(
                    parsed_output,
                    txid,
                    block_id=block_id,
                    timestamp=transaction['time'],
                    source=NODE.BCH.source,
                )

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

                ready_to_accept(block.number, len(transactions))
            finally:
                REDIS_STORAGE.set('READY', 1)

    active_block = REDIS_STORAGE.get('ACTIVE-BLOCK')
    if active_block:
        active_block = str(REDIS_STORAGE.get('ACTIVE-BLOCK').decode())
        LOGGER.info(f'CURRENTLY PROCESSING BLOCK {str(active_block)}')


def save_transaction(tx, block_id=None):
    """
        tx must be parsed by 'BCHN._parse_transaction()'
    """
    tx_check = Transaction.objects.filter(txid=tx['txid'])
    if tx_check.exists():
        tx_obj = tx_check.last()
        tx_obj.block_id = block_id
        tx_obj.save()
        return
    
    txid = tx['txid']
    if len(tx['inputs']) and 'coinbase' in tx['inputs'][0].keys():
        return

    for output in tx['outputs']:
        index = output['index']
        address = output['address']
        value = output['value']

        process_output(
            output,
            txid,
            block_id=block_id,
            timestamp=tx['timestamp'],
            source=NODE.BCH.source,
        )

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
            value = output['value']

            block, created = BlockHeight.objects.get_or_create(number=block)
            transaction_check = Transaction.objects.filter(
                txid=tx_hash,
                address__address=address,
                index=index
            )
            if transaction_check.exists():
                # Check if transaction wallet matches with address's wallet
                # Correct this if not matching
                # Also, Mark as unspent, just in case it's already marked spent
                # and also update the blockheight
                _txn = transaction_check.first()
                if _txn.wallet == _txn.address.wallet:
                    transaction_check.update(spent=False, value=value, blockheight=block)
                else:
                    transaction_check.update(wallet=_txn.address.wallet, value=value, spent=False, blockheight=block)
                
                for obj in transaction_check:
                    saved_utxo_ids.append(obj.id)
            else:
                # Keep track of token_data structure if there are changes in source data
                # Refer to function docstring for expected structure
                output_data = {
                    'index': index,
                    'value': value,
                    'address': address,
                    'token_data': output['token_data'],
                }
                processed_output_data = process_output(
                    output_data,
                    tx_hash,
                    block_id=block.id,
                    source=NODE.BCH.source,
                )
                created = processed_output_data['created']
                if created:
                    if not block.requires_full_scan:
                        qs = BlockHeight.objects.filter(id=block.id)
                        count = qs.first().transactions.count()
                        qs.update(processed=True, transactions_count=count)
     
            parse_tx_wallet_histories.delay(tx_hash, immediate=True)

        # Mark other transactions of the same address as spent
        Transaction.objects \
            .filter(address__address=address, spent=False) \
            .exclude(id__in=saved_utxo_ids) \
            .update(spent=True)

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
                    # Check if transaction wallet matches with address's wallet
                    # Correct this if not matching
                    # Also, Mark as unspent, just in case it's already marked spent
                    # and also update the blockheight
                    _txn = transaction_obj.first()
                    if _txn.wallet == _txn.address.wallet:
                        transaction_obj.update(spent=False, blockheight=block)
                    else:
                        transaction_obj.update(wallet=_txn.address.wallet, spent=False, blockheight=block)
                    
                    for obj in transaction_obj:
                        saved_utxo_ids.append(obj.id)
        
        # Mark other transactions of the same address as spent
        Transaction.objects.filter(
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


def _get_wallet_hash(tx_hex):
    wallet_hash = None
    try:
        tx = NODE.BCH._decode_raw_transaction(tx_hex)
        input0 = tx['vin'][0]
        input0_tx = NODE.BCH._get_raw_transaction(input0['txid'])
        vout_data = input0_tx['vout'][input0['vout']]
        if vout_data['scriptPubKey']['type'] == 'pubkeyhash':
            address = vout_data['scriptPubKey']['addresses'][0]
            try:
                address_obj = Address.objects.get(address=address)
                if address_obj.wallet:
                    wallet_hash = address_obj.wallet.wallet_hash
            except Address.DoesNotExist:
                pass
    except:
        pass
    return wallet_hash


@shared_task(bind=True, queue='broadcast', max_retries=7)
def broadcast_transaction(self, transaction, txid, broadcast_id, auto_retry=True):
    LOGGER.info(f'Broadcasting {txid}: {transaction}')
    txn_check = Transaction.objects.filter(txid=txid)
    success = False

    if txn_check.exists():
        success = True
    else:
        txn_broadcast = TransactionBroadcast.objects.get(id=broadcast_id)
        if txn_broadcast.num_retries < 7:
            try:
                try:
                    txid = NODE.BCH.broadcast_transaction(transaction)
                    if txid:
                        success = True
                    else:
                        if auto_retry: self.retry(countdown=1)
                except Exception as exc:
                    LOGGER.exception(exc)
                    error = str(exc)
                    if 'already have transaction' in error:
                        success = True
                    else:
                        TransactionBroadcast.objects.filter(id=broadcast_id).update(
                            error=error
                        )
            except AttributeError as exc:
                LOGGER.exception(exc)
                if auto_retry: self.retry(countdown=1)

    if success:
        TransactionBroadcast.objects.filter(id=broadcast_id).update(
            date_succeeded=timezone.now()
        )
        process_mempool_transaction_fast(txid, transaction, True)
    else:
        if txn_broadcast.num_retries < 7:
            TransactionBroadcast.objects.filter(id=broadcast_id).update(
                num_retries=models.F('num_retries') + 1
            )
            if txn_broadcast.num_retries >= 3:
                if txn_broadcast.num_retries == 3:
                    # Do a wallet utxo rescan if failed 3 times
                    wallet_hash = _get_wallet_hash(transaction)
                    rescan_utxos(wallet_hash)
                if auto_retry: self.retry(countdown=3)


@shared_task(queue='broadcast', max_retries=2)
def bulk_rebroadcast():
    """ Find broadcasts that got interrupted by temporary disruptions in the background
    task queue (e.g. due to deployments, redis or celery issues, congestions) and rebroadcast them. """
    threshold = timezone.now() - timezone.timedelta(seconds=30)
    pending_broadcasts = TransactionBroadcast.objects.filter(
        date_received__lte=threshold,
        date_succeeded__isnull=True,
        num_retries__lt=7
    )
    for broadcast in pending_broadcasts:
        broadcast_transaction.delay(
            broadcast.tx_hex,
            broadcast.txid,
            broadcast.id,
            auto_retry=False
        )


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


@shared_task(queue='contract_history')
def parse_contract_history(txid, address, tx_fee=None, senders=[], recipients=[]):
    BCH_OR_SLP = 'bch_or_slp'
    if type(tx_fee) is str:
        tx_fee = float(tx_fee)

    parser = HistoryParser(txid, address=address)
    parsed_history = parser.parse()

    for key, value in parsed_history.items():
        record_type = value['record_type']
        amount = value['diff']

        processed_recipients = process_history_recpts_or_senders(recipients, key, BCH_OR_SLP)
        processed_senders = process_history_recpts_or_senders(senders, key, BCH_OR_SLP)

        if record_type == 'outgoing':
            if key == BCH_OR_SLP:
                amount = abs(amount) - ((tx_fee / 100000000) or 0)
                amount = round(amount, 8)
            amount = abs(amount) * -1

        if amount == 0: continue

        bch_prefix = 'bitcoincash:'
        if settings.BCH_NETWORK != 'mainnet':
            bch_prefix = 'bchtest:'

        txns = Transaction.objects.filter(
            txid=txid,
            address__address__startswith=bch_prefix
        )
        spent_txns = Transaction.objects.filter(
            spending_txid=txid,
            address__address__startswith=bch_prefix,
        )

        tx_timestamp = txns.filter(tx_timestamp__isnull=False).aggregate(_max=models.Max('tx_timestamp'))['_max']
        date_created = txns.filter(date_created__isnull=False).aggregate(_max=models.Max('date_created'))['_max']

        cashtoken_ft = None
        cashtoken_nft = None
        token_obj = None

        ct_category = None
        if key.startswith('ct/'):
            ct_category = key.split('ct/')[1]

        if key == BCH_OR_SLP:
            txns = txns.filter(token__name='bch')
            spent_txns = spent_txns.filter(token__name='bch')
        elif ct_category:
            _txns = txns.filter(
                models.Q(cashtoken_ft__category=ct_category) | \
                models.Q(cashtoken_nft__category=ct_category),
            )
            if _txns.exists():
                txns = _txns
                ft_tx = txns.filter(cashtoken_ft_id=ct_category).last()
                if ft_tx:
                    cashtoken_ft = ft_tx.cashtoken_ft
                if not cashtoken_ft:
                    nft_tx = txns.filter(cashtoken_nft__category=ct_category).last()
                    if nft_tx:
                        cashtoken_nft = nft_tx.cashtoken_nft
            else:
                # Get the cashtoken record if transaction does not have this info
                ct_recipient = None
                ct_index = None
                for i, _recipient in enumerate(processed_recipients):
                    ct_index = i
                    if _recipient[2] == ct_category:
                        ct_recipient = _recipient
                        break

                if key.startswith('ct') and ct_recipient:
                    token_obj, _ = Token.objects.get_or_create(tokenid=settings.WT_DEFAULT_CASHTOKEN_ID)
                    token_id = ct_recipient[2]
                    nft_capability = ct_recipient[4]
                    nft_commitment = ct_recipient[5]
                    if token_id:
                        if not cashtoken_ft:
                            cashtoken_ft, _ = CashFungibleToken.objects.get_or_create(category=token_id)
                            cashtoken_ft.fetch_metadata()
                        if not cashtoken_nft and nft_capability:
                            cashtoken_nft, _ = CashNonFungibleToken.objects.get_or_create(
                                category=token_id,
                                capability=nft_capability,
                                commitment=nft_commitment,
                                current_txid=txid,
                                current_index=ct_index
                            )

        txn = txns.last()
        spent_txn = spent_txns.last()

        if not txn and not spent_txn: continue
        if not token_obj:
            _txn = txn or spent_txn
            token_obj = _txn.token

        _address = Address.objects.filter(address=address)
        _address = _address.first()
        
        history_check = ContractHistory.objects.filter(
            address=_address,
            txid=txid,
            token=token_obj,
            cashtoken_ft=cashtoken_ft,
            cashtoken_nft=cashtoken_nft
        )
        if history_check.exists():
            history_check.update(
                record_type=record_type,
                amount=amount,
                token=token_obj,
                cashtoken_ft=cashtoken_ft,
                cashtoken_nft=cashtoken_nft
            )
            if tx_fee and processed_senders and processed_recipients:
                history_check.update(
                    tx_fee=tx_fee,
                    senders=processed_senders,
                    recipients=processed_recipients
                )
            if tx_timestamp:
                history_check.update(tx_timestamp=tx_timestamp)
                resolve_wallet_history_usd_values.delay(txid=txid, is_contract=True)
        else:
            history = ContractHistory(
                address=_address,
                txid=txid,
                record_type=record_type,
                amount=amount,
                token=token_obj,
                cashtoken_ft=cashtoken_ft,
                cashtoken_nft=cashtoken_nft,
                tx_fee=tx_fee,
                senders=processed_senders,
                recipients=processed_recipients,
                date_created=date_created,
                tx_timestamp=tx_timestamp,
            )

            try:
                history.save()
                resolve_wallet_history_usd_values.delay(txid=txid, is_contract=True)
            except IntegrityError as exc:
                LOGGER.exception(exc)


@shared_task(bind=True, queue='wallet_history_1')
def parse_wallet_history(self, txid, wallet_handle, tx_fee=None, senders=[], recipients=[], proceed_with_zero_amount=False):
    stack_frames = get_stack_frames(1, 5)
    trigger_info = "\n\t >> ".join([format_stack_frame(frame) for frame in stack_frames])
    LOGGER.info(f"PARSING WALLET HISTORY | {txid} | {wallet_handle}\nTriggered from {trigger_info}")
    wallet_hash = wallet_handle.split('|')[1]
    
    wallet = Wallet.objects.get(wallet_hash=wallet_hash)

    # Do not record wallet history record if all senders and recipients are from the same wallet (i.e. UTXO consolidation txs)
    sender_addresses = set([i[0] for i in senders if i[0]])
    senders_check = Address.objects.filter(address__in=sender_addresses, wallet=wallet)
    recipient_addresses = set([i[0] for i in recipients if i[0]])
    recipients_check = Address.objects.filter(address__in=recipient_addresses, wallet=wallet)
    if len(sender_addresses) == senders_check.count():
        if len(recipient_addresses) == recipients_check.count():
            # Remove wallet history record of this, if any
            WalletHistory.objects.filter(txid=txid).delete()
            return

    parser = HistoryParser(txid, wallet_hash=wallet_hash)
    parsed_history = parser.parse()

    if type(tx_fee) is str:
        tx_fee = float(tx_fee)
    
    BCH_OR_SLP = 'bch_or_slp'

    # parsed_history.keys() = ['bch_or_slp', 'ct']
    for key in parsed_history.keys():
        ct_category = None
        if key.startswith("ct/"):
            ct_category = key.split("ct/")[1]

        data = parsed_history[key]
        record_type = data['record_type']
        amount = data['diff']
        change_address = data['change_address']

        _recipients = None
        if change_address:
            _recipients = [info for info in recipients if info[0] != change_address]

        processed_recipients = process_history_recpts_or_senders(_recipients or recipients, key, BCH_OR_SLP)
        processed_senders = process_history_recpts_or_senders(senders, key, BCH_OR_SLP)

        if wallet.wallet_type == 'bch':
            # Correct the amount for outgoing, subtract the miner fee if given and maintain negative sign
            if record_type == 'outgoing':
                if key == BCH_OR_SLP:
                    amount = abs(amount) - ((tx_fee / 100000000) or 0)
                    amount = round(amount, 8)
                amount = abs(amount) * -1

            # Don't save a record if resulting amount is zero
            is_zero_amount = amount == 0
            if is_zero_amount and not proceed_with_zero_amount:
                # skip this key and continue with the next key
                continue

            if is_zero_amount:
                record_type = ''

            bch_prefix = 'bitcoincash:'
            if settings.BCH_NETWORK != 'mainnet':
                bch_prefix = 'bchtest:'

            txns = Transaction.objects.filter(
                txid=txid,
                address__address__startswith=bch_prefix
            )
            spent_txns = Transaction.objects.filter(
                spending_txid=txid,
                address__address__startswith=bch_prefix,
            )

            tx_timestamp = txns.filter(tx_timestamp__isnull=False).aggregate(_max=models.Max('tx_timestamp'))['_max']
            date_created = txns.filter(date_created__isnull=False).aggregate(_max=models.Max('date_created'))['_max']

            cashtoken_ft = None
            cashtoken_nft = None
            token_obj = None

            if key == BCH_OR_SLP:
                txns = txns.filter(token__name='bch')
                spent_txns = spent_txns.filter(token__name='bch')
            elif ct_category:
                _txns = txns.filter(
                    models.Q(cashtoken_ft__category=ct_category) | \
                    models.Q(cashtoken_nft__category=ct_category),
                )
                if _txns.exists():
                    txns = _txns
                    ft_tx = txns.filter(cashtoken_ft_id=ct_category).last()
                    if ft_tx:
                        cashtoken_ft = ft_tx.cashtoken_ft
                    if not cashtoken_ft:
                        nft_tx = txns.filter(cashtoken_nft__category=ct_category).last()
                        if nft_tx:
                            cashtoken_nft = nft_tx.cashtoken_nft
                else:
                    # Get the cashtoken record if transaction does not have this info
                    ct_recipient = None
                    ct_index = None
                    for i, _recipient in enumerate(processed_recipients):
                        ct_index = i
                        if _recipient[2] == ct_category:
                            ct_recipient = _recipient
                            break

                    if key.startswith("ct") and ct_recipient:
                        token_obj, _ = Token.objects.get_or_create(tokenid=settings.WT_DEFAULT_CASHTOKEN_ID)
                        token_id = ct_recipient[2]
                        nft_capability = ct_recipient[4]
                        nft_commitment = ct_recipient[5]
                        if token_id:
                            if not cashtoken_ft:
                                cashtoken_ft, _ = CashFungibleToken.objects.get_or_create(category=token_id)
                                cashtoken_ft.fetch_metadata()
                            if not cashtoken_nft and nft_capability:
                                cashtoken_nft, _ = CashNonFungibleToken.objects.get_or_create(
                                    category=token_id,
                                    capability=nft_capability,
                                    commitment=nft_commitment,
                                    current_txid=txid,
                                    current_index=ct_index
                                )

        elif wallet.wallet_type == 'slp':
            if key != BCH_OR_SLP:
                return

            txns = Transaction.objects.filter(
                txid=txid,
                address__address__startswith='simpleledger:'
            )

        txn = txns.last()
        spent_txn = spent_txns.last()

        if not txn and not spent_txn: continue

        if not token_obj:
            _txn = txn or spent_txn
            token_obj = _txn.token

        history_check = WalletHistory.objects.filter(
            wallet=wallet,
            txid=txid,
            token=token_obj,
            cashtoken_ft=cashtoken_ft,
            cashtoken_nft=cashtoken_nft
        )
        if history_check.exists():
            history_check.update(
                record_type=record_type,
                amount=amount,
                token=token_obj,
                cashtoken_ft=cashtoken_ft,
                cashtoken_nft=cashtoken_nft
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
            
            # Check if this transaction has output_fiat_amounts from broadcast
            txn_broadcast = TransactionBroadcast.objects.filter(txid=txid).first()
            if txn_broadcast and txn_broadcast.output_fiat_amounts:
                fiat_amounts = {}
                
                if record_type == 'incoming':
                    # For incoming transactions, sum fiat amounts for outputs going to this wallet
                    for output_idx, output_data in txn_broadcast.output_fiat_amounts.items():
                        recipient = output_data.get('recipient')
                        if not recipient:
                            continue
                        
                        # Check if this recipient address belongs to the wallet
                        if Address.objects.filter(wallet=wallet, address=recipient).exists():
                            fiat_currency = output_data.get('fiat_currency')
                            fiat_amount = output_data.get('fiat_amount')
                            
                            if fiat_currency and fiat_amount:
                                amount_float = float(fiat_amount)
                                if fiat_currency in fiat_amounts:
                                    fiat_amounts[fiat_currency] += amount_float
                                else:
                                    fiat_amounts[fiat_currency] = amount_float
                
                elif record_type == 'outgoing':
                    # For outgoing transactions, only set fiat_amounts if ALL inputs are from this wallet
                    all_inputs_from_wallet = True
                    for sender in processed_senders:
                        if sender and sender[0]:
                            if not Address.objects.filter(wallet=wallet, address=sender[0]).exists():
                                all_inputs_from_wallet = False
                                break
                    
                    if all_inputs_from_wallet:
                        # Sum fiat amounts for outputs NOT going back to this wallet (exclude change)
                        for output_idx, output_data in txn_broadcast.output_fiat_amounts.items():
                            recipient = output_data.get('recipient')
                            if not recipient:
                                continue
                            
                            # Skip if recipient is a change address (back to wallet)
                            if Address.objects.filter(wallet=wallet, address=recipient).exists():
                                continue
                            
                            fiat_currency = output_data.get('fiat_currency')
                            fiat_amount = output_data.get('fiat_amount')
                            
                            if fiat_currency and fiat_amount:
                                amount_float = float(fiat_amount)
                                if fiat_currency in fiat_amounts:
                                    fiat_amounts[fiat_currency] += amount_float
                                else:
                                    fiat_amounts[fiat_currency] = amount_float
                
                # Update fiat_amounts if we found any
                if fiat_amounts:
                    history_check.update(fiat_amounts=fiat_amounts)
        else:
            history = WalletHistory(
                wallet=wallet,
                txid=txid,
                record_type=record_type,
                amount=amount,
                token=token_obj,
                cashtoken_ft=cashtoken_ft,
                cashtoken_nft=cashtoken_nft,
                tx_fee=tx_fee,
                senders=processed_senders,
                recipients=processed_recipients,
                date_created=date_created,
                tx_timestamp=tx_timestamp,
            )

            # Check if this transaction has a price_log from broadcast
            txn_broadcast = TransactionBroadcast.objects.select_related('price_log').filter(txid=txid).first()
            if txn_broadcast and txn_broadcast.price_log:
                history.price_log = txn_broadcast.price_log
            
            # Check if this transaction has output_fiat_amounts from broadcast
            if txn_broadcast and txn_broadcast.output_fiat_amounts:
                fiat_amounts = {}
                
                if record_type == 'incoming':
                    # For incoming transactions, sum fiat amounts for outputs going to this wallet
                    for output_idx, output_data in txn_broadcast.output_fiat_amounts.items():
                        recipient = output_data.get('recipient')
                        if not recipient:
                            continue
                        
                        # Check if this recipient address belongs to the wallet
                        if Address.objects.filter(wallet=wallet, address=recipient).exists():
                            fiat_currency = output_data.get('fiat_currency')
                            fiat_amount = output_data.get('fiat_amount')
                            
                            if fiat_currency and fiat_amount:
                                amount_float = float(fiat_amount)
                                if fiat_currency in fiat_amounts:
                                    fiat_amounts[fiat_currency] += amount_float
                                else:
                                    fiat_amounts[fiat_currency] = amount_float
                
                elif record_type == 'outgoing':
                    # For outgoing transactions, only set fiat_amounts if ALL inputs are from this wallet
                    # Check if all input addresses belong to this wallet
                    all_inputs_from_wallet = True
                    for sender in processed_senders:
                        if sender and sender[0]:  # sender[0] is the address
                            if not Address.objects.filter(wallet=wallet, address=sender[0]).exists():
                                all_inputs_from_wallet = False
                                break
                    
                    if all_inputs_from_wallet:
                        # Sum fiat amounts for outputs NOT going back to this wallet (exclude change)
                        for output_idx, output_data in txn_broadcast.output_fiat_amounts.items():
                            recipient = output_data.get('recipient')
                            if not recipient:
                                continue
                            
                            # Skip if recipient is a change address (back to wallet)
                            if Address.objects.filter(wallet=wallet, address=recipient).exists():
                                continue
                            
                            fiat_currency = output_data.get('fiat_currency')
                            fiat_amount = output_data.get('fiat_amount')
                            
                            if fiat_currency and fiat_amount:
                                amount_float = float(fiat_amount)
                                if fiat_currency in fiat_amounts:
                                    fiat_amounts[fiat_currency] += amount_float
                                else:
                                    fiat_amounts[fiat_currency] = amount_float
                
                # Set fiat_amounts if we found any
                if fiat_amounts:
                    history.fiat_amounts = fiat_amounts

            try:
                history.save()

                resolve_wallet_history_usd_values.delay(txid=txid)

                if history.tx_timestamp:
                    try:
                        parse_wallet_history_market_values(history.id)
                        history.refresh_from_db()
                    except Exception as exception:
                        LOGGER.exception(exception)

                try:
                    # Do not send notifications for amounts less than or equal to 0.00001
                    if abs(amount) > 0.00001:
                        LOGGER.info(f"PUSH_NOTIF: wallet_history for #{history.txid} | {history.amount}")
                        send_wallet_history_push_notification(history)
                    else:
                        return send_wallet_history_push_notification_nft(history)
                except Exception as exception:
                    LOGGER.exception(exception)
            except IntegrityError as exc:
                LOGGER.exception(exc)

        # merchant wallet check
        merchant_check = Merchant.objects.filter(wallet_hash=wallet.wallet_hash)
        if merchant_check.exists():
            for merchant in merchant_check.all():
                merchant.last_update = timezone.now()
                merchant.active = True
                merchant.save()

                # update latest_transaction in POS devices
                pos_devices = PosDevice.objects.filter(merchant=merchant)
                for device in pos_devices:
                    device.populate_latest_history_record()

        # for older token records
        if (
            txn and
            txn.token and
            txn.token.tokenid and
            txn.token.tokenid != settings.WT_DEFAULT_CASHTOKEN_ID and
            (txn.token.token_type is None or txn.token.mint_amount is None)
        ):
            get_token_meta_data(txn.token.tokenid, async_image_download=True)
            txn.token.refresh_from_db()

        if txn and txn.token and txn.token.is_nft:
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
        else:
            return send_wallet_history_push_notification_nft(history)
    except Exception as exception:
        LOGGER.exception(exception)


@shared_task(bind=True, queue='post_save_record', max_retries=10)
def transaction_post_save_task(self, address, transaction_id, blockheight_id=None):
    # txid = Transaction.objects.values_list("txid", flat=True).filter(id=transaction_id).first()
    # if not txid: return
    txid = None
    try:
        txn_obj = Transaction.objects.get(id=transaction_id)
        txid = txn_obj.txid
        if txn_obj.post_save_processed:
            return transaction_id
    except Transaction.DoesNotExist:
        return transaction_id
    
    if not txid: return transaction_id
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
    parse_contract = is_p2sh_address(address)
    bch_tx = NODE.BCH.get_transaction(txid)
    slp_tx = None
    if parse_slp:
        slp_tx = NODE.SLP.get_transaction(txid, parse_slp=True)

    if parse_slp and not isinstance(slp_tx, dict) and not slp_tx.get('valid'):
        self.retry(countdown=5)
        return transaction_id

    if not bch_tx:
        self.retry(countdown=5)
        return transaction_id

    tx_timestamp = bch_tx['timestamp']
    # use batch update to not trigger the post save signal and potentially create an infinite loop
    parsed_tx_timestamp = datetime.fromtimestamp(tx_timestamp).replace(tzinfo=pytz.UTC)
    Transaction.objects.filter(txid=txid, tx_timestamp__isnull=True).update(tx_timestamp=parsed_tx_timestamp)

    # Mark BCH tx inputs as spent
    mark_transaction_inputs_as_spent(bch_tx)

    # Extract tx_fee, senders, and recipients
    tx_fee = bch_tx['tx_fee']
    senders = { 'bch': [], 'slp': [] }
    recipients = { 'bch': [], 'slp': [] }

    # Parse SLP senders and recipients
    if parse_slp and wallet_type == 'slp':
        senders['slp'] = [parse_utxo_to_tuple(i, is_slp=True) for i in slp_tx['inputs'] if 'amount' in i]
        if 'outputs' in slp_tx:
            recipients['slp'] = [parse_utxo_to_tuple(i, is_slp=True) for i in slp_tx['outputs']]

    # Parse BCH senders and recipients or contracts
    if wallet_type == 'bch' or parse_contract:
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
            # Marking Transction object as spent is already done earlier in this function

            txn_check = Transaction.objects.filter(
                txid=tx_input['txid'],
                index=tx_input['spent_index'],
            )
            if not txn_check.exists(): continue

            txn_obj = txn_check.last()
            if txn_obj.token.is_nft:
                wallet_nft_tokens = WalletNftToken.objects.filter(acquisition_transaction=txn_obj)
                if wallet_nft_tokens.exists():
                    wallet_nft_tokens.update(
                        date_dispensed = timezone.now(),
                        dispensation_transaction = txn_obj
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

    # Parse BCH tx outputs
    for tx_output in bch_tx['outputs']:
        txn_check = Transaction.objects.filter(
            txid=bch_tx['txid'],
            address__address=tx_output['address'],
            index=tx_output['index']
        )

        if not txn_check.exists():
            process_output(
                tx_output,
                bch_tx['txid'],
                block_id=blockheight_id,
                timestamp=bch_tx['timestamp'],
                source=NODE.BCH.source,
            )

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
    
    if parse_contract:
        parse_contract_history.delay(
            txid,
            address,
            tx_fee=tx_fee,
            senders=senders['bch'],
            recipients=recipients['bch']
        )
    
    # Mark txn as processed
    Transaction.objects.filter(id=transaction_id).update(post_save_processed=timezone.now())

    return list(set(wallets))


@shared_task(queue='rescan_utxos')
def rescan_utxos(wallet_hash, full=False):
    wallet = Wallet.objects.get(wallet_hash=wallet_hash)
    if full:
        addresses = wallet.addresses.all()
    else:
        addresses = wallet.addresses.filter(transactions__spent=False)

    # delete cached bch balance
    cache = settings.REDISKV
    bch_cache_key = f'wallet:balance:bch:{wallet_hash}'
    cache.delete(bch_cache_key)

    # delete cached token balance
    ct_cache_keys = cache.keys(f'wallet:balance:token:{wallet_hash}:*')
    if ct_cache_keys:
        cache.delete(*ct_cache_keys)

    # delete cached wallet history
    history_cache_keys = cache.keys(f'wallet:history:{wallet_hash}:*')
    if history_cache_keys:
        cache.delete(*history_cache_keys)

    try:
        for address in addresses:
            if wallet.wallet_type == 'bch':
                get_bch_utxos(address.address)
            elif wallet.wallet_type == 'slp':
                get_slp_utxos(address.address)
        wallet.last_utxo_scan_succeeded = True
        wallet.save()
    except Exception as exc:
        wallet.last_utxo_scan_succeeded = False
        wallet.save()
        raise exc


def rebuild_address_wallet_history(address, tx_count_limit=30, ignore_txids=[]):
    data = get_bch_transactions(address, chipnet=settings.BCH_NETWORK == 'chipnet')
    if isinstance(data, list) and tx_count_limit:
        data = data[:tx_count_limit]
    tx_hashes = []
    for tx_info in data:
        tx_hash = tx_info['tx_hash']
        try:
            if tx_hash in ignore_txids: continue
            parse_tx_wallet_histories(tx_hash)
            tx_hashes.append(tx_hash)
        except Exception as exception:
            LOGGER.error(f'Unable to parse {address} tx {tx_hash} | {str(exception)}')
    return tx_hashes


@shared_task(queue='wallet_history_1')
def rebuild_wallet_history(wallet_hash):
    wallet = Wallet.objects.get(wallet_hash=wallet_hash)
    if not wallet: return { "success": False, "error": "Wallet does not exist" }
    if wallet.wallet_type != 'bch':
        return { "success": False, "error": f"Only supports 'bch' wallets, got '{wallet.wallet_type}'" }

    tx_hashes = []
    for address in wallet.addresses.all():
        tx_hashes += rebuild_address_wallet_history(address, ignore_txids=tx_hashes)

    return { "success": True, "txs": tx_hashes }


@shared_task(queue='wallet_history_1', max_retries=3)
def parse_tx_wallet_histories(txid, txn_details=None, proceed_with_zero_amount=False, immediate=False, force=False):
    history_check = WalletHistory.objects.filter(txid=txid)
    if history_check.exists():
        if force:
            history_check.delete()
        else:
            return

    LOGGER.info(f"PARSE TX WALLET HISTORIES: {txid}")
    if txn_details:
        bch_tx = txn_details
    else:
        bch_tx = NODE.BCH.get_transaction(txid)

    if 'tx_fee' in bch_tx.keys():
        tx_fee = bch_tx['tx_fee']
    else:
        tx_fee = math.ceil(bch_tx['size'] * settings.TX_FEE_RATE)

    tx_timestamp = None
    if 'timestamp' in bch_tx.keys():
        tx_timestamp = bch_tx['timestamp']

    # Mark inputs as spent
    mark_transaction_inputs_as_spent(bch_tx)

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
    for i, utxo in enumerate(utxos, 1):
        is_output = not utxo['is_input']

        force_create = False
        # If this tx has no saved outputs (which is required for recording wallet history)
        # force create a transaction output record
        if i == len(utxos) and not has_saved_output: force_create = True

        if not force_create and not is_output:
            txn_check = Transaction.objects.filter(txid=utxo['txid'], index=utxo['index'])
            if txn_check.exists():
                continue

            inp_wallet_hash = Address.objects.filter(address=utxo['address']).values_list("wallet__wallet_hash", flat=True).first()
            if inp_wallet_hash not in wallet_hashes:
                continue

        if is_output: has_saved_output = True

        # utxo variable here is similar to BCHN._parse_output()
        # so it's okay to pass the dict as it is
        #
        # send_client_acknowledgement is conditional somehow,
        # added this condition to keep logic before refactoring
        send_client_acknowledgement = bool(utxo['token_data'])
        process_output(
            utxo,
            utxo['txid'],
            timestamp=tx_timestamp if is_output else None,
            source=NODE.BCH.source,
            force_create=force_create,
            send_client_acknowledgement=send_client_acknowledgement,
        )

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
def resolve_wallet_history_usd_values(txid=None, is_contract=False):
    CURRENCY = "USD"
    RELATIVE_CURRENCY = "BCH"
    MODEL = ContractHistory if is_contract else WalletHistory

    queryset = MODEL.objects.filter(
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
        wallet_histories = MODEL.objects.filter(
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
        # "https://api.coingecko.com/api/v3/coins/bitcoin-cash/market_chart/range?" + \
        "https://pro-api.coingecko.com/api/v3/coins/bitcoin-cash/market_chart/range?" + \
        f"vs_currency={CURRENCY}" + \
        f"&from={from_timestamp.timestamp()}" + \
        f"&to={to_timestamp.timestamp()}",
        headers={
            'x-cg-pro-api-key': settings.COINGECKO_API_KEY
        }
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
        wallet_history_obj = WalletHistory.objects.select_related(
            'price_log',
            'price_log__currency_ft_token',
            'price_log__currency_ft_token__info'
        ).get(id=wallet_history_id)
    except WalletHistory.DoesNotExist:
        return

    if wallet_history_obj.tx_timestamp is None:
        return

    # block for bch txs and ft cashtokens only
    if wallet_history_obj.token.name != "bch" and not wallet_history_obj.cashtoken_ft:
        return
    
    # do not proceed if both usd_price and market_prices are already populated
    # if wallet_history_obj.usd_price and wallet_history_obj.market_prices:
    #     return

    LOGGER.info(" | ".join([
        f"WALLET_HISTORY_MARKET_VALUES",
        f"{wallet_history_obj.id}:{wallet_history_obj.txid}",
        f"{wallet_history_obj.tx_timestamp}",
    ]))

    # resolves the currencies needed to store for the wallet history
    currencies = ["USD", "PHP"]
    try:
        if wallet_history_obj.wallet and wallet_history_obj.wallet.preferences and wallet_history_obj.wallet.preferences.selected_currency:
            currencies.append(wallet_history_obj.wallet.preferences.selected_currency)
    except Wallet.preferences.RelatedObjectDoesNotExist:
        pass

    currencies = [c.upper() for c in currencies if isinstance(c, str) and len(c)]
    print(f"currencies | {currencies}")

    market_prices = wallet_history_obj.market_prices or {}
    if wallet_history_obj.usd_price:
        market_prices["USD"] = wallet_history_obj.usd_price

    # NEW: Use price_log if available (from broadcast API)
    if wallet_history_obj.price_log:
        price_log = wallet_history_obj.price_log
        
        bch_to_asset_multiplier = 1
        if wallet_history_obj.cashtoken_ft and price_log.currency_ft_token:
            # Token/fiat price stored directly
            # price_log.price_value is stored as "tokens per fiat" (e.g., 531 MUSD per 1 PHP)
            # but client expects "fiat per token" (e.g., 0.00188 PHP per 1 MUSD)
            if price_log.currency_ft_token.category == wallet_history_obj.cashtoken_ft.category:
                # Invert to get fiat per token
                market_prices[price_log.currency] = float(1 / price_log.price_value)
        else:
            # BCH/fiat price
            market_prices[price_log.currency] = float(price_log.price_value)
            
            # Get token/BCH conversion if needed
            if wallet_history_obj.cashtoken_ft:
                ft_bch_log = get_ft_bch_price_log(
                    wallet_history_obj.cashtoken_ft.category,
                    timestamp=wallet_history_obj.tx_timestamp
                )
                if ft_bch_log:
                    bch_to_asset_multiplier = 1 / ft_bch_log.price_value
                    market_prices[price_log.currency] = float(price_log.price_value * bch_to_asset_multiplier)
        
        wallet_history_obj.market_prices = market_prices
        if "USD" in market_prices and not wallet_history_obj.usd_price:
            wallet_history_obj.usd_price = Decimal(market_prices["USD"])
        for currency, price in wallet_history_obj.market_prices.items():
            if isinstance(price, Decimal):
                wallet_history_obj.market_prices[currency] = float(price)
        wallet_history_obj.save()
        
        return {
            "id": wallet_history_obj.id,
            "txid": wallet_history_obj.txid,
            "tx_timestamp": str(wallet_history_obj.tx_timestamp),
            "market_prices": market_prices,
            "used_price_log_id": price_log.id
        }

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

    print(f"asset_price_logs | {asset_price_logs}")

    bch_to_asset_multiplier = 1
    if wallet_history_obj.cashtoken_ft and currencies:
        ft_bch_price_log = get_ft_bch_price_log(
            wallet_history_obj.cashtoken_ft.category,
            timestamp=timestamp,
        )
        if not ft_bch_price_log: return "No price"

        bch_to_asset_multiplier = 1 / ft_bch_price_log.price_value


    # sorting above is closest timestamp last so the loop below ends up with the closest one
    for price_log in asset_price_logs:
        market_prices[price_log.currency] = price_log.price_value * bch_to_asset_multiplier

    # last resort for resolving prices, only for new txs
    missing_currencies = [c for c in currencies if c not in market_prices]
    tx_age = (timezone.now() - timestamp).total_seconds()
    if tx_age < 30 and len(missing_currencies):
        bch_rates = get_latest_bch_rates(currencies=missing_currencies)
        print(f"bch_rates | {bch_rates}")
        for currency in missing_currencies:
            bch_rate = bch_rates.get(currency.lower(), None)
            if bch_rate:
                market_prices[currency] = bch_rate[0] * bch_to_asset_multiplier

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


def _process_mempool_transaction(tx_hash, tx_hex=None, immediate=False, force=False):
    tx_check = Transaction.objects.filter(txid=tx_hash)
    if tx_check.exists() and not force:
        return
    
    LOGGER.info('Processing mempool tx: ' + tx_hash)
    proceed = False
    tx = None
    if tx_hex and immediate:
        tx = NODE.BCH.parse_transaction_from_hex(tx_hex)

        output_addresses = []
        for output in tx['outputs']:
            if 'address' in output.keys():
                output_addresses.append(output['address'])
        output_addresses_check = Address.objects.filter(address__in=output_addresses)


        if output_addresses_check.exists():
            proceed = True
        else:
            input_txids = [x['txid'] for x in tx['inputs'] if 'txid' in x.keys()]
            input_txids_check = Transaction.objects.filter(txid__in=input_txids)
            if input_txids_check.exists():
                proceed = True

            else:
                proceed = False
    else:
        proceed = True

    if proceed:
        if not tx:
            tx = NODE.BCH.get_transaction(tx_hash)

        # if passed through the throttled task queue
        # skip processing if it already has at least 1 confirmation
        if not immediate:
            if 'confirmations' in tx.keys() and not force:
                LOGGER.info('Skipped confirmed tx: ' + str(tx_hash))
                return

        inputs = tx['inputs']
        outputs = tx['outputs']

        if 'coinbase' in inputs[0].keys():
            return

        save_histories = False
        inputs_data = []

        # Mark inputs as spent
        mark_transaction_inputs_as_spent(tx)

        for _input in inputs:
            txid = _input['txid']
            value = _input['value']
            index = _input['spent_index']

            tx_check = Transaction.objects.filter(txid=txid, index=index)
            if tx_check.exists():
                address = None
                for _tx in tx_check:
                    if not _tx.address: continue
                    address = _tx.address.address

                if address:
                    # save wallet history only if tx is associated with a wallet
                    if tx_check.filter(wallet__isnull=False).exists():
                        save_histories = True

                    subscription = Subscription.objects.filter(address__address=address)
                    if subscription.exists():
                        inputs_data.append({
                            "token": "bch",
                            "address": address,
                            "value": value,
                            "outpoint_txid": txid,
                            "outpoint_index": index,
                        })

        for output in outputs:
            if 'address' in output:
                bchaddress = output['address']

                address_check = Address.objects.filter(address=bchaddress)
                if address_check.exists():
                    value = output['value']

                    if 'time' in tx.keys():
                        timestamp = tx['time']
                    else:
                        timestamp = timezone.now().timestamp()

                    processed_output_data = process_output(
                        output,
                        tx_hash,
                        timestamp=timestamp,
                        source=NODE.BCH.source,
                        inputs=inputs_data,
                    )
                    token_id = processed_output_data['token_id']
                    decimals = processed_output_data['decimals']
                    amount = str(processed_output_data['amount'])
                    created = processed_output_data['created']
                    obj_id = processed_output_data['transaction_id']

                    if obj_id and created:
                        # Publish MQTT message
                        data = {
                            'txid': tx_hash,
                            'recipient': bchaddress,
                            'token': token_id,
                            'decimals': decimals,
                            'amount': amount,
                            'value': value
                        }
                        addr_obj = None
                        if token_id.startswith('ct/'):
                            # Include cashtoken address in data
                            try:
                                addr_obj = Address.objects.get(address=bchaddress)
                                if addr_obj.token_address:
                                    data['recipient_cashtoken_address'] = addr_obj.token_address
                            except Address.DoesNotExist:
                                pass
                            # If NFT, include NFT data (capability and commitment)
                            if 'nft' in output['token_data'].keys():
                                data['nft'] = output['token_data']['nft']

                        try:
                            LOGGER.info('Sending MQTT message: ' + str(data))
                            # Somehow this topic will only be used when output is cashtoken,
                            # keeping it this way to preserve logic during refactor
                            if addr_obj and addr_obj.wallet and addr_obj.wallet.wallet_hash:
                                hash_obj = SHA256.new(addr_obj.wallet.wallet_hash.encode('utf-8'))
                                hashed_wallet_hash = hash_obj.hexdigest()
                                topic = f"transactions/{hashed_wallet_hash}/{bchaddress}"
                            else:
                                topic = f"transactions/address/{bchaddress}"
                            publish_message(topic, data, qos=1)
                        except:
                            LOGGER.error(f"Failed to send mqtt for tx | {tx_hash} | {bchaddress}")

        if save_histories:
            LOGGER.info(f"Parsing wallet history of tx({tx_hash})")
            if immediate:
                parse_tx_wallet_histories(tx_hash, txn_details=tx, immediate=True, force=force)
            else:
                parse_tx_wallet_histories.delay(tx_hash, txn_details=tx, force=force)

@shared_task(
  base=HeimdallTask,
  queue='mempool_processing_throttled',
  heimdall={
    'rate_limit': RateLimit((20, 60))
  }
)
def process_mempool_transaction_throttled(tx_hash, tx_hex=None, immediate=False):
    _process_mempool_transaction(tx_hash, tx_hex, immediate)


@shared_task(
  base=HeimdallTask,
  queue='mempool_processing_fast',
  heimdall={
    'rate_limit': RateLimit((100, 60))
  }
)
def process_mempool_transaction_fast(tx_hash, tx_hex=None, immediate=False):
    _process_mempool_transaction(tx_hash, tx_hex, immediate)


@shared_task(queue='save_record')
def get_latest_bch_prices_task(currencies=[]):
    assert isinstance(currencies, list)
    for index, currency in enumerate(currencies):
        assert isinstance(currency, str), f"[{index}] not a string: {currency}"

    currencies = [currency.upper().strip() for currency in currencies]
    max_age = 30
    if 'ARS' in currencies:
        max_age = 300
    results = get_and_save_latest_bch_rates(currencies=currencies, max_age=max_age)
    response = {}
    for currency, asset_price_log in results.items():
        response[currency] = {
            'currency': asset_price_log.currency,
            'timestamp': str(asset_price_log.timestamp),
            'source': asset_price_log.source,
        }
    return response


def get_latest_bch_price(currency):
    """
        Fetch latest price BCH price from a currency.
        Has a mechanism to check other running tasks to prevent
        running duplicate tasks

        Returns: AssetPriceLog | None
    """
    assert isinstance(currency, str), "currency param is not a string"
    currency = currency.upper().strip()
    max_age = 30
    if currency == 'ARS':
        max_age = 300
    get_latest = lambda: AssetPriceLog.objects.filter(
        currency=currency,
        relative_currency="BCH",
        timestamp__gt = timezone.now()-timezone.timedelta(seconds=max_age),
        timestamp__lte = timezone.now()+timezone.timedelta(seconds=max_age),
    ).order_by("-timestamp").first()

    latest = get_latest()
    if latest: return latest

    task_key = f"latest_bch_price_task_{currency}"
    existing_task_id = REDIS_STORAGE.get(task_key)
    if existing_task_id:
        existing_task_id = existing_task_id.decode()
        existing_task = celery_app.AsyncResult(existing_task_id)
        try:
            existing_task.get(timeout=30)
        except TimeoutError:
            pass
        finally:
            latest = get_latest()
            if latest: return latest

    task = get_latest_bch_prices_task.delay(currencies=[currency])
    REDIS_STORAGE.set(task_key, task.id)
    try:
        task.get()
        latest = get_latest()
        if latest: return latest
    finally:
        REDIS_STORAGE.delete(task_key)


class MarketPriceTaskQueueManager(celery_app.Task):
    abstract = True

    class RedisKeys:
        LAST_CALL_TIMESTAMP = "last_call_timestamp"
        # COIN_IDS = "market_price__coin_ids"
        # CURRENCIES = "market_price__currencies"

        PAIR_TASK_ID_MAP = "market_price__pair_task_ids_map"
        PAIR_QUEUE = "market_price__pair_queue"

    @classmethod
    def enqueue(cls, coin_id="", currency=""):
        """
            Add a pair to the queue. Returns a dict that contain either keys:

            task_id:str - the price rate for the pair is already being fetched by the task
            wait_time:float - the pair is queued but needs to wait since the last fetch was recent
            run:bool - the pair is queued and last fetch was not recent (note that this doesn't actually do the fetching)
        """
        pair_name = cls.construct_pair(coin_id=coin_id, currency=currency)
        if not pair_name: return

        existing_task_id = cls.get_running_task_id(pair_name)
        if existing_task_id: return dict(task_id=existing_task_id)

        cls.queue_pairs(pair_name)

        wait_time = cls.get_wait_time()
        if wait_time > 0: return dict(wait_time=wait_time)

        return dict(run=True)

    @classmethod
    def get_latest(cls, coin_id="", currency="", pair_name="", return_id=False):
        if pair_name: 
            deconstructed = cls.deconstruct_pair_name(pair_name)
            coin_id = deconstructed["coin_id"]
            currency = deconstructed["currency"]

        filter_kwargs = {
            'currency': CoingeckoAPI.parse_currency(currency).upper(),
            'relative_currency': CoingeckoAPI.coin_id_to_asset_name(coin_id),
            'timestamp__gt': timezone.now()-timezone.timedelta(seconds=30),
            'timestamp__lte': timezone.now()+timezone.timedelta(seconds=30),
        }
        
        if CoingeckoAPI.parse_currency(currency).upper() == 'ARS':
            filter_kwargs['source'] = 'coingecko-yadio'
            
        query = AssetPriceLog.objects.filter(**filter_kwargs).order_by("-timestamp")

        if return_id: query = query.values_list("id", flat=True)

        if query.first():
            return query.first()
        else:
            return get_latest_bch_price(currency)

    @classmethod
    def queue_pairs(cls, *pair_names):
        return REDIS_STORAGE.sadd(cls.RedisKeys.PAIR_QUEUE, *pair_names)
    
    @classmethod
    def get_wait_time(cls):
        last_call_timestamp = REDIS_STORAGE.get(cls.RedisKeys.LAST_CALL_TIMESTAMP) or 0
        if isinstance(last_call_timestamp, bytes):
            last_call_timestamp = float(last_call_timestamp)

        now = timezone.now().timestamp()
        wait_time = last_call_timestamp - (now-5)
        return wait_time

    @classmethod
    def get_running_task_id(cls, pair_name):
        if not pair_name or not isinstance(pair_name, str): return
        result = REDIS_STORAGE.hget(cls.RedisKeys.PAIR_TASK_ID_MAP, pair_name)
        if isinstance(result, bytes): result = result.decode()
        return result

    @classmethod
    def construct_pair(cls, coin_id="", currency=""):
        coin_id = CoingeckoAPI.asset_name_to_coin_id(coin_id)
        if not coin_id: return
        currency = CoingeckoAPI.parse_currency(currency)
        if not currency: return

        return ":".join([coin_id, currency])

    @classmethod
    def deconstruct_pair_name(cls, pair_name):
        if isinstance(pair_name, bytes): pair_name = pair_name.decode()
        coin_id, currency = pair_name.split(":", maxsplit=1)
        return dict(coin_id=coin_id, currency=currency)

    def __call__(self, *args, **kwargs):
        """
            - Flush all queued and transfer to pair/task_id map
            - Execute core task
            - Clear remove the pair/task_id keys
        """
        task_id = self.request.id
        pair_set = REDIS_STORAGE.smembers(self.RedisKeys.PAIR_QUEUE)
        pair_task_id_map = {pair: task_id for pair in pair_set}

        if not pair_set: return

        pipeline = REDIS_STORAGE.pipeline()
        pipeline.hset(self.RedisKeys.PAIR_TASK_ID_MAP, mapping=pair_task_id_map)
        pipeline.srem(self.RedisKeys.PAIR_QUEUE, *pair_set)
        pipeline.set(self.RedisKeys.LAST_CALL_TIMESTAMP, timezone.now().timestamp())
        pipeline.execute()

        try:
            coin_ids = set()
            currencies = set()      
            for pair in pair_set:
                pair_dict = self.deconstruct_pair_name(pair)
                coin_ids.add(pair_dict["coin_id"])
                currencies.add(pair_dict["currency"])

            LOGGER.info(f"market_price_task | coin_ids={coin_ids} | currencies={currencies}")

            coingecko_api = CoingeckoAPI()
            result = coingecko_api.get_market_prices(
                currencies=currencies, coin_ids=coin_ids, save=True
            )
            return result
        finally:
            REDIS_STORAGE.hdel(
                self.RedisKeys.PAIR_TASK_ID_MAP,
                *pair_task_id_map.keys(),
            )
            super().__call__(*args, **kwargs)


@shared_task(base=MarketPriceTaskQueueManager, bind=True, queue="save_record")
def market_price_task(self, *args, **kwargs):
    """
        - This will run after the base class function is done
        - Return value here wont be the tasks result
    """
    pass

@shared_task(queue="save_record")
def get_latest_market_price_task(coin_id:str, currency:str):
    latest = MarketPriceTaskQueueManager.get_latest(coin_id=coin_id, currency=currency)
    if latest: return latest

    queue_result = MarketPriceTaskQueueManager.enqueue(coin_id=coin_id, currency=currency)
    if not queue_result: return

    qr = [queue_result]
    wait_time = queue_result.get("wait_time", 0)
    if wait_time > 0:
        time.sleep(wait_time)
        queue_result = MarketPriceTaskQueueManager.enqueue(coin_id=coin_id, currency=currency)
        qr.append(queue_result)

    LOGGER.info(f"coin_id={coin_id} | currency={currency} | queue_result={qr}")

    if not queue_result: return

    existing_task_id = queue_result.get("task_id")
    if existing_task_id:
        existing_task_id = existing_task_id.decode()
        existing_task = celery_app.AsyncResult(existing_task_id)
        try:
            existing_task.get(timeout=30)
        except TimeoutError:
            pass

    if queue_result.get("run"):
        # NOTE: may lead to deadlocks(due to waiting for tasks within a task)
        # https://docs.celeryq.dev/en/latest/reference/celery.result.html#celery.result.AsyncResult.wait
        market_price_task.delay().wait(timeout=30, interval=1)

    return MarketPriceTaskQueueManager.get_latest(coin_id=coin_id, currency=currency)
