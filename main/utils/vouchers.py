from vouchers.models import *

from django.db.models import Q


def is_key_nft(category, recipient_address):
    vouchers = Voucher.objects.filter(category=category)

    # we differentiate the lock and key NFT by checking if the recipient is a vault address
    # as the lock NFT always goes to the vault address and never gets sent anywhere
    vault_recipients = Vault.objects.filter(
        Q(address=recipient_address) |
        Q(token_address=recipient_address)
    )

    __is_key_nft = vouchers.exists() and not vault_recipients.exists()
    return __is_key_nft
