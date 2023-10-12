from vouchers.models import Voucher


def is_key_nft(category):
    vouchers = Voucher.objects.filter(category=category)
    return vouchers.exists()
