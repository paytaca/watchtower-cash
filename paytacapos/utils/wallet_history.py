import re
from paytacapos.models import PosWalletHistory, Merchant

from main.models import WalletHistory, Wallet, Address


def __get_address_path_regex__():
    MAX_POS_DIGITS = 4
    address_path_regex = fr"0/\d+(\d{{{MAX_POS_DIGITS}}})"
    return address_path_regex


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

    address_path_regex = __get_address_path_regex__()
    for address_path in address_paths:
        regex_test = re.match(address_path_regex, address_path)
        if not regex_test: continue

        posid = int(regex_test.group(1))
        pos_wallet_history_obj, _ = PosWalletHistory.objects.update_or_create(
            wallet_history=wallet_history,
            posid=posid,
        )
        return pos_wallet_history_obj


def populate_pos_wallet_history(wallet_hash):
    wallet = Wallet.objects.filter(wallet_hash=wallet_hash).first()
    if not wallet:
        return

    address_path_regex = __get_address_path_regex__()
    address_qs = Address.objects.filter(wallet=wallet) \
        .filter(address_path__regex=address_path_regex)
    address_paths = address_qs.values_list("address_path", flat=True)

    posids = {re.match(address_path_regex, path).group(1) for path in address_paths}
    results = {}
    for posid in posids:
        wallet_hisory_qs = WalletHistory.objects.filter_pos(wallet_hash, posid=int(posid))
        print(f"{wallet_hash} | {posid} | {wallet_hisory_qs.values_list('id', flat=True)}")
        print(f"{wallet_hisory_qs.query}")
        wallet_hisory_ids = wallet_hisory_qs.values_list("id", flat=True)
        for wallet_history_id in wallet_hisory_ids:
            PosWalletHistory.objects.update_or_create(
                wallet_history_id=wallet_history_id, posid=posid,
            )
        results[posid] = [*wallet_hisory_qs.values_list("txid", flat=True)]
    return results


def populate_pos_wallet_histories_with_merchant():
    """
    Run once to populate all existing merchants' POS wallet histories.
    """
    results = {}
    for wallet_hash in Merchant.objects.values_list("wallet_hash", flat=True).distinct():
        results[wallet_hash] = populate_pos_wallet_history(wallet_hash)
    return results
