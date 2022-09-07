from django.db.models import OuterRef, Subquery, Sum, F, Value
from django.db.models.functions import Coalesce, Greatest
from ..models import (
    LongAccount,
)
from .websocket import send_long_account_update


def get_position_offer_suggestions(amount=0, duration_seconds=0, low_liquidation_multiplier=0.9, high_liquidation_multiplier=10):
    # NOTE: long_amount_needed is an estimate and may be off by a bit from the actual amount needed, this is due to;
    # missing oracle price
    long_amount_needed = (amount / low_liquidation_multiplier) - amount

    return LongAccount.objects.filter(
        auto_accept_allowance__gte=long_amount_needed,
        min_auto_accept_duration__lte=duration_seconds,
        max_auto_accept_duration__gte=duration_seconds,
    ).order_by('auto_accept_allowance')


def consume_long_account_allowance(long_address, long_input_sats):
    querylist = LongAccount.objects.filter(address=long_address)
    resp = querylist.update(auto_accept_allowance= Greatest(F("auto_accept_allowance") - long_input_sats, Value(0)))

    wallet_hashes =  querylist.values_list('wallet_hash', flat=True).distinct()
    for wallet_hash in wallet_hashes:
        send_long_account_update(wallet_hash, action="consume_allowance")
    return resp
