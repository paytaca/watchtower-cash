from vouchers.models import *

from django.utils import timezone
from django.conf import settings

import requests


def is_key_nft(category, bch_value):
    vouchers = Voucher.objects.filter(category=category)
    __is_key_nft = vouchers.exists() and bch_value == 1000  # lock NFT value will always be > 1000
    return __is_key_nft


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