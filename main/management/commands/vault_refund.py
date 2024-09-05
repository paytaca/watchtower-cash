from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from paytacapos.models import PosDevice, Merchant
from vouchers.vault import get_device_vault, get_merchant_vault

import requests


class Command(BaseCommand):
    help = "Refund accidentally sent BCH from device (and/or) merchant vault contract, back to the sender"

    def add_arguments(self, parser):
        parser.add_argument("-pid", "--pos_device_id", type=int, default=0)
        parser.add_argument("-mid", "--merchant_id", type=int, default=0)

        parser.add_argument("-mra", "--merchant_refund_amount", type=int, default=0)
        parser.add_argument("-pra", "--pos_device_refund_amount", type=int, default=0)

        parser.add_argument("-sa", "--sender_address", type=str, default='')
        parser.add_argument("-spk", "--sender_pubkey", type=str, default='')


    def handle(self, *args, **options):
        pos_device_id = options['pos_device_id']
        merchant_id = options['merchant_id']
        merchant_refund_amount = options['merchant_refund_amount'] * 1e8
        pos_device_refund_amount = options['pos_device_refund_amount'] * 1e8
        sender_address = options['sender_address']
        sender_pubkey = options['sender_pubkey']

        pos_device = PosDevice.objects.get(id=pos_device_id)
        merchant = Merchant.objects.get(id=merchant_id)
        device_payload = get_device_vault(pos_device.id)['payload']
        merchant_payload = get_merchant_vault(merchant.id)['payload']

        device_payload['params']['refundAmount'] = pos_device_refund_amount
        device_payload['params']['sender'] = {
            'address': sender_address,
            'pubkey': sender_pubkey,
        }
        merchant_payload['params']['refundAmount'] = merchant_refund_amount
        merchant_payload['params']['sender'] = {
            'address': sender_address,
            'pubkey': sender_pubkey,
        }

        url = settings.VAULT_EXPRESS_URLS['device']
        url = f'{url}/emergency-refund'
        response = requests.post(url, json=device_payload)
        response = response.json()

        if response['success']:
            txid = response['txid']
            self.stdout.write(self.style.SUCCESS(f'Refunded {refund_amount} BCH to {sender_address} from device vault contract!')) 
            self.stdout.write(self.style.SUCCESS(f'TXID: {txid}')) 


        url = settings.VAULT_EXPRESS_URLS['merchant']
        url = f'{url}/emergency-refund'
        response = requests.post(url, json=merchant_payload)
        response = response.json()

        if response['success']:
            txid = response['txid']
            self.stdout.write(self.style.SUCCESS(f'Refunded {refund_amount} BCH to {sender_address} from merchant vault contract!')) 
            self.stdout.write(self.style.SUCCESS(f'TXID: {txid}')) 
