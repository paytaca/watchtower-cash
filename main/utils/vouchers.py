from vouchers.models import *


def is_key_nft(category, bch_value):
    vouchers = Voucher.objects.filter(category=category)
    __is_key_nft = vouchers.exists() and bch_value == 1000  # lock NFT value will always be > 1000
    return __is_key_nft
