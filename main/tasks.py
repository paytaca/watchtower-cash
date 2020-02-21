"""
sample
"""
from __future__ import absolute_import, unicode_literals
import logging
from celery import shared_task
import request
from main.models import BlockHeight, Token, Transaction
import json


LOGGER = logging.getLogger(__name__)

@shared_task(queue='save_record')
def save_record(tokenid, address, transactionid, blockheightid=None):
    """
    Handles updating records in database
    """
    token_obj = Token.objects.get(id=tokenid)
    transaction_obj = Transaction.objects.get(id=transactionid)
    address_obj, created = SlpAddress.objects.get_or_create(
        token=token_obj,
        address=address,
    )
    transaction_obj.amount = amount
    transaction_obj.save()
    address_obj.add(transaction_obj)
    if blockheight is not None:
        blockheight_instance = BlockHeight.objects.get(id=blockheightid)
        blockheight_instance.processed = True
        blockheight_instance.save()
    msg = f'FOUND DEPOSIT {amount} -> {address_data['slpAddress']}'
    LOGGER.INFO(msg)

@shared_task(queue='deposit_filter')
def deposit_filter(txn_id, blockheightid):
    """
    This function check if transaction id 
    """
    transaction_qs = Transaction.objects.filter(txid=txn_id)
    if not transaction_qs.exists():
        transaction_url = 'https://rest.bitcoin.com/v2/slp/txDetails/%s' % (txn_id)
        transaction_response = requests.get(transaction_url)
        if transaction_response.status_code == 200:
            transaction_data = json.loads(transaction_response.text)
            if transaction_data['tokenInfo']['transactionType'].lower() == 'send':
                transaction_token_id = transaction_data['tokenInfo']['tokenIdHex']
                token_query = Token.objects.filter(tokenid=transaction_token_id)
                if token_query.exists():
                    amount = float(this['tokenInfo']['sendOutputs'][1]) / 100000000
                    legacy = this['retData']['vout'][1]['scriptPubKey']['addresses'][0]
                    address_url = 'https://rest.bitcoin.com/v2/address/details/%s' % legacy
                    address_response = requests.get(address_url)
                    address_data = json.loads(address_response.text)
                    if not 'error' in address_data.keys():
                        transaction_obj, created = Transaction.objects.get_or_create(txid=txn_id)
                        if created:
                            token_obj = token_query.first()
                            save_record(
                                tokenidtoken_obj.id,
                                address_data['slpAddress'],
                                transaction_obj.id,
                                blockheightid
                            )

@shared_task(queue='kickstart_blockheight')
def kickstart_blockheight():
    """
    This task intended for checking new blockheight.
    This will beat every 3 seconds.
    """
    url = 'https://rest.bitcoin.com/v2/blockchain/getBlockchainInfo'
    try:
        resp = requests.get(url)
        number = json.loads(resp.text)['blocks']
    except Exception as exc:
        self.retry(countdown=60)
    obj, created = BlockHeight.objects.get_or_create(number=number)
    if created:
        blockheight.delay(obj.id)

@shared_task(queue='blockheight')
def blockheight(id):
    """
    This task process missed transactions per blockheight
    """
    blockheight_instance= BlockHeight.objects.get(id=id)
    heightnumber = blockheight_instance.number
    url = 'https://rest.bitcoin.com/v2/block/detailsByHeight/%s' % heightnumber
    resp = requests.get(url)
    data = json.loads(resp.text)
    if 'error' not in data.keys():
        transactions = data['tx']
        for txn_id in transactions:
            deposit_filter.delay(txn_id, blockheight_instance.id)
            

@shared_task(bind=True, queue='slpfountainhead', max_retries=10)
def slpfountainhead(self):
    """
    This is a live stream of SLP transactions
    """
    resp = requests.get(url, stream=True)
    logger.info('socket ready in : %s' % source)
    previous = ''
    for content in resp.iter_content(chunk_size=1024*1024):
        loaded_data = None
        try:
            content = content.decode('utf8')
            if '"tx":{"h":"' in previous:
                data = previous + content
                data = data.strip().split('data: ')[-1]
                loaded_data = json.loads(data)
        except (ValueError, UnicodeDecodeError, TypeError) as exc:
            msg = traceback.format_exc()
            LOGGER.error(msg)
        except Exception as exc:
            self.retry(countdown=60)
        previous = content
        if loaded_data is not None:
            if len(loaded_data['data']) > 0:
                info = loaded_data['data'][0]
                if 'slp' in info.keys():
                    if 'detail' in info['slp'].keys():
                        if 'tokenIdHex' in info['slp']['detail'].keys():
                            if info['slp']['detail']['tokenIdHex'] == settings.SPICE_TOKEN_ID:
                                amount = float(info['slp']['detail']['outputs'][0]['amount'])
                                slp_address = info['slp']['detail']['outputs'][0]['address']
                                if 'tx' in info.keys():
                                    txn_id = info['tx']['h']
                                    token_obj = token_query.first()
                                    address_obj, created = SlpAddress.objects.get_or_create(
                                        token=token_obj,
                                        address=address_data['slpAddress'],
                                    )
                                    transaction_obj, created = Transaction.objects.get_or_create(txid=txn_id)
                                    if created:
                                        transaction_obj.amount = amount
                                        transaction_obj.save()
                                        address_obj.add(transaction_obj)
                                        msg = f'FOUND DEPOSIT {amount} -> {address_data['slpAddress']}'
                                        LOGGER.INFO(msg)
                                        save_record.delay(
                                            info['slp']['detail']['tokenIdHex'],
                                            slp_address,
                                            transaction_obj.id,
                                        )