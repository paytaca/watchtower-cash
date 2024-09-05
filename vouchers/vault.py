from django.conf import settings

from paytacapos.models import Merchant, PosDevice
from vouchers.models import PosDeviceVault, MerchantVault

from bitcash.keygen import public_key_to_address

import requests


def get_merchant_vault(merchant_id):
    merchant = Merchant.objects.get(id=merchant_id)
    payload = {
        'params': {
            'merchant': {
                'verificationCategory': merchant.verification_category,
                'pubkey': {
                    'merchant': merchant.pubkey,
                    # 'device': None
                }
            },
            'funder': {
                'address': settings.VOUCHER_FEE_FUNDER_ADDRESS,
                'wif': settings.VOUCHER_FEE_FUNDER_WIF
            },
            # 'sender': {
            #     'pubkey': '',
            #     'address': '',
            # },
            # 'refundAmount': None,
        },
        'options': {
            'network': settings.BCH_NETWORK
        }
    }
    url = settings.VAULT_EXPRESS_URLS['merchant']
    url = f'{url}/compile'
    response = requests.post(url, json=payload)
    contract = response.json()
    return {
        'contract': contract,
        'payload': payload
    }


def get_device_vault(pos_device_id):
    pos_device = PosDevice.objects.get(id=pos_device_id)
    merchant_vault = get_merchant_vault(pos_device.merchant.id)
    payload = {
        'params': {
            'merchant': {
                'address': public_key_to_address(pubkey),
                'pubkey': pubkey,
                'vaultTokenAddress': pos_device.merchant.vault.token_address,
                'scriptHash': merchant_vault['contract']['scriptHash'],
                'verificationCategory': pos_device.merchant.verification_category,
                # 'voucher': {
                #     'category': None
                # }
            },
            'funder': {
                'address': settings.VOUCHER_FEE_FUNDER_ADDRESS,
                'wif': settings.VOUCHER_FEE_FUNDER_WIF,
            },
            # 'sender': {
            #     'pubkey': '',
            #     'address': '',
            # },
            # 'refundAmount': None,
            # 'amount': None
        },
        'options': {
            'network': setings.BCH_NETWORK
        }
    }
    url = settings.VAULT_EXPRESS_URLS['device']
    url = f'{url}/compile'
    response = requests.post(url, json=payload)
    contract = response.json()
    return {
        'contract': contract,
        'payload': payload
    }


def create_device_vault(pos_device_id, pubkey):
    pos_device = PosDevice.objects.get(id=pos_device_id)

    if not pubkey: return
    if pos_device.vault: return

    address = bytearray.fromhex(pubkey)
    device_vault = get_device_vault(pos_device.id)
    contract = device_vault['contract']

    # delete old vaults
    PosDeviceVault.objects.filter(pos_device=pos_device).delete()

    PosDeviceVault(
        pos_device=pos_device,
        pubkey=pubkey,
        address=contract['address'],
        token_address=contract['tokenAddress']
    ).save()


def create_merchant_vault(merchant_id, pubkey):
    merchant = Merchant.objects.get(id=merchant_id)
    
    if not pubkey: return
    if merchant.vault: return

    merchant_vault = get_merchant_vault(merchant.id)
    contract = merchant_vault['contract']

    # delete old vaults
    MerchantVault.objects.filter(merchant=merchant).delete()

    MerchantVault(
        merchant=merchant,
        address=contract['address'],
        token_address=contract['tokenAddress'],
    ).save()