from vouchers.models import *


def is_key_nft(address, category):
    vaults = Vault.objects.filter(address=address)

    if vaults.exists():
        cashdrop_nft_pairs = Voucher.objects.filter(
            key_category=category,
            vault=vaults.first()
        )
        lock_nft_category = None

        if cashdrop_nft_pairs.exists():
            lock_nft_category = cashdrop_nft_pairs.first().lock_category
            return True, lock_nft_category
            
    return False, None
