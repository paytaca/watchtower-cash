from paytacapos.models import PosPaymentRequest
from vouchers.models import *

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from django.utils import timezone
from django.conf import settings

from bitcash.keygen import public_key_to_address
from celery import shared_task
import requests


# key_nft = False, means your checking for lock NFTs
def is_voucher(category, amount, key_nft=False):
    vouchers = Voucher.objects.filter(category=category)
    is_voucher = vouchers.exists()
    dust = 1000

    is_valid_amount = amount > dust
    if key_nft:
        is_valid_amount = amount == dust or amount == 0.00001

    return is_voucher and is_valid_amount


def update_purelypeer_voucher(txid, category):
    headers = {
        'purelypeer-proof-auth-header': settings.PURELYPEER_AUTH_HEADER
    }
    payload = {
        'txid': txid,
        'category': category
    }
    url = f'{settings.PURELYPEER_API_URL}/key_nfts/claimed/'
    response = requests.post(url, json=payload, headers=headers)


def flag_claimed_voucher(txid, category):
    vouchers = Voucher.objects.filter(category=category)
    vouchers.update(
        claimed=True,
        claim_txid=txid,
        date_claimed=timezone.now()
    )
    update_purelypeer_voucher(txid, category)


def process_pending_payment_requests(pubkey, amount, payload):
    payment_requests = PosPaymentRequest.objects.filter(
        pos_device__vault__pubkey=pubkey,
        amount__lte=amount,
        paid=False
    )
    if not payment_requests.exists(): return

    url = f'{settings.VOUCHER_EXPRESS_URL}/release'
    response = requests.post(url, json=payload)
    response = response.json()

    if response['success']:
        payment_requests.update(paid=True)


@shared_task(queue='vouchers')
def claim_voucher(category, pubkey):
    address = bytearray.fromhex(pubkey)
    address = public_key_to_address(address)
    payload = {
        'params': {
            'category': category,
            'merchant': {
                'pubkey': pubkey,
            },
        },
        'options': {
            'network': 'mainnet'
        }
    }
    url = f'{settings.VOUCHER_EXPRESS_URL}/claim'
    response = requests.post(url, json=payload)
    response = response.json()

    if not response['success']: return

    txid = response['txid']
    data = { 'update_type': 'voucher_processed' }
    room_name = address.replace(':','_') + '_'
    channel_layer = get_channel_layer()

    flag_claimed_voucher(txid, category)
    async_to_sync(channel_layer.group_send)(
        f"{room_name}", 
        {
            "type": "send_update",
            "data": data
        }
    )

    url = f'{settings.VOUCHER_EXPRESS_URL}/vault-balance'
    response = requests.post(url, json=payload)
    response = response.json()
    balance = response['balance']

    process_pending_payment_requests(pubkey, balance, payload)