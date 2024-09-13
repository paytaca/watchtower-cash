from django.conf import settings

from main.utils.address_converter import bch_address_converter
from paytacapos.models import Merchant, PosDevice
from vouchers.models import (
    PosDeviceVault,
    MerchantVault,
    VerificationTokenMinter,
)

from bitcash.keygen import public_key_to_address
import requests


def get_merchant_vault(merchant_id, pubkey=None):
    merchant = Merchant.objects.get(id=merchant_id)
    __pubkey = pubkey or merchant.vault.pubkey
    payload = {
        'params': {
            'merchant': {
                'verificationCategory': merchant.minter.category,
                'pubkey': {
                    'merchant': __pubkey,
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
    url = settings.VAULT_EXPRESS_URLS['merchant'] + '/compile'
    response = requests.post(url, json=payload)
    contract = response.json()
    return {
        'contract': contract,
        'payload': payload
    }


def get_device_vault(pos_device_id, pubkey=None):
    pos_device = PosDevice.objects.get(id=pos_device_id)
    merchant_vault = get_merchant_vault(pos_device.merchant.id)
    __pubkey = pubkey or pos_device.vault.pubkey
    pubkey_arr = bytearray.fromhex(__pubkey)

    payload = {
        'params': {
            'merchant': {
                'address': public_key_to_address(pubkey_arr),
                'pubkey': __pubkey,
                'vaultTokenAddress': pos_device.merchant.vault.token_address,
                'scriptHash': merchant_vault['contract']['scriptHash'],
                'verificationCategory': pos_device.merchant.minter.category,
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
            'network': settings.BCH_NETWORK
        }
    }
    url = settings.VAULT_EXPRESS_URLS['device'] + '/compile'
    response = requests.post(url, json=payload)
    contract = response.json()
    return {
        'contract': contract,
        'payload': payload
    }


def create_device_vault(pos_device_id, pubkey=None):
    pos_device = PosDevice.objects.get(id=pos_device_id)

    if not pubkey: return

    try:
        pos_device.merchant.vault
        pos_device.merchant.minter
    except:
        return

    try:
        if pos_device.vault: return
    except:
        pass

    device_vault = get_device_vault(pos_device.id, pubkey=pubkey)
    contract = device_vault['contract']

    PosDeviceVault.objects.filter(pos_device=pos_device).delete()
    PosDeviceVault.objects.create(
        pos_device=pos_device,
        pubkey=pubkey,
        address=contract['address'],
        token_address=contract['tokenAddress']
    )


def create_verification_token_minter(merchant_id, address, category):
    merchant = Merchant.objects.get(id=merchant_id)
    token_address = bch_address_converter(address)
    VerificationTokenMinter.objects.create(
        merchant=merchant,
        category=category,
        address=address,
        token_address=token_address
    )


def create_merchant_vault(merchant_id, pubkey=None, minter_address=None, minter_category=None):
    merchant = Merchant.objects.get(id=merchant_id)

    if not pubkey: return
    if not minter_address: return
    if not minter_category: return
    
    try:
        if merchant.vault and merchant.minter: return
    except:
        create_verification_token_minter(
            merchant.id,
            minter_address,
            minter_category
        )

    merchant_vault = get_merchant_vault(merchant.id, pubkey=pubkey)
    contract = merchant_vault['contract']

    MerchantVault.objects.filter(merchant=merchant).delete()
    merchant_vault = MerchantVault.objects.create(
        merchant=merchant,
        address=contract['address'],
        token_address=contract['tokenAddress'],
        pubkey=pubkey
    )