from vouchers.models import *

from django.utils import timezone


def is_key_nft(category, bch_value):
    vouchers = Voucher.objects.filter(category=category)
    __is_key_nft = vouchers.exists() and bch_value == 1000  # lock NFT value will always be > 1000
    return __is_key_nft


def flag_claimed_voucher(txid, category):
    vouchers = Voucher.objects.filter(category=category)
    vouchers.update(
        claimed=True,
        claim_txid=txid,
        date_claimed=timezone.now()
    )