import re
from paytacapos.models import PosWalletHistory

from main.models import WalletHistory, Address


def link_wallet_history(wallet_history:WalletHistory):
    if not wallet_history.wallet: return

    wallet = wallet_history.wallet
    addresses = set()
    for recipient_data in wallet_history.recipients:
        address = recipient_data[0]
        addresses.add(address)

    address_paths = Address.objects \
        .filter(address__in=addresses, wallet=wallet) \
        .values_list("address_path", flat=True)

    MAX_POS_DIGITS = 4
    address_path_regex = fr"0/\d+(\d{{{MAX_POS_DIGITS}}})"
    for address_path in address_paths:
        regex_test = re.match(address_path_regex, address_path)
        if not regex_test: continue

        posid = int(regex_test.group(1))
        pos_wallet_history_obj, _ = PosWalletHistory.objects.update_or_create(
            wallet_history=wallet_history,
            posid=posid,
        )
        return pos_wallet_history_obj
