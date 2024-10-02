from paytacapos.models import PosPaymentRequest
from vouchers.models import *
from vouchers.vault import get_device_vault, get_merchant_vault

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from django.utils import timezone
from django.conf import settings
from django.db.models import Q

from bitcash.keygen import public_key_to_address
from celery import shared_task
import requests, logging


logger = logging.getLogger(__name__)


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


@shared_task(queue='vouchers')
def process_pending_payment_requests(address, senders):
    device_vaults = PosDeviceVault.objects.filter(address=address)
    merchant_vaults = MerchantVault.objects.filter(
        models.Q(address__in=senders) |
        models.Q(token_address__in=senders)
    )

    if not device_vaults.exists(): return
    if not merchant_vaults.exists(): return

    device_vault = device_vaults.first()
    payment_requests = PosPaymentRequest.objects.filter(
        pos_device__vault__pubkey=device_vault.pubkey,
        paid=False
    )
    payment_request = payment_requests.first()
    
    if not payment_requests.exists(): return

    payload = get_device_vault(device_vault.pos_device.id)['payload']
    prefix = settings.VAULT_EXPRESS_URLS['device']
    
    url = prefix + '/compile'
    response = requests.post(url, json=payload)
    response = response.json()
    balance = response['balance']

    if payment_request.amount > balance: return

    url = prefix + '/release'
    payload['params']['amount'] = payment_request.amount * 1e8
    response = requests.post(url, json=payload)
    response = response.json()

    if response['success']:
        payment_requests.update(paid=True)


def send_voucher_payment_notification(txid, category, senders):
    device_vault = PosDeviceVault.objects.filter(address__in=senders)
    device_vault = device_vault.first()
    merchant_vault = device_vault.pos_device.merchant.vault

    data = { 'update_type': 'voucher_processed' }
    pubkey = bytearray.fromhex(merchant_vault.pubkey)
    address = public_key_to_address(pubkey)
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


def process_device_vault(category, recipient_address, senders):
    device_vaults = PosDeviceVault.objects.filter(address=recipient_address)
    if device_vaults.exists():
        logger.info('PROCESSING DEVICE VAULT...')

        voucher = Voucher.objects.filter(category=category)
        voucher.update(sent=True)

        pos_device = device_vaults.first().pos_device
        url = settings.VAULT_EXPRESS_URLS['device'] + '/send-tokens'
        payload = get_device_vault(pos_device.id)['payload']
        payload['params']['merchant']['voucher'] = { 'category': category }
        response = requests.post(url, json=payload)
        result = response.json()


def process_merchant_vault(txid, category, recipient_address, senders):
    merchant_vaults = MerchantVault.objects.filter(address=recipient_address)
    if merchant_vaults.exists():
        merchant = merchant_vaults.first().merchant
        pos_device_vaults = PosDeviceVault.objects.filter(address__in=senders)
        if not pos_device_vaults.exists(): return

        logger.info('PROCESSING MERCHANT VAULT...')

        url = settings.VAULT_EXPRESS_URLS['merchant'] + '/claim'
        payload = get_merchant_vault(merchant.id)['payload'] 
        pos_device = pos_device_vaults.first().pos_device
        payload['params']['merchant']['voucher'] = { 'category': category }
        payload['params']['merchant']['pubkey']['device'] = pos_device.vault.pubkey

        response = requests.post(url, json=payload)
        result = response.json()

        if not result['success']: return
        send_voucher_payment_notification(txid, category, senders)


@shared_task(queue='process_key_nft')
def process_key_nft(txid, category, recipient_address, senders):
    process_device_vault(category, recipient_address, senders)
    process_merchant_vault(txid, category, recipient_address, senders)