from main.models import WalletActivity, WalletHistory

SATOSHIS_PER_BCH = 100_000_000
BIGINT_MAX = 9_223_372_036_854_775_807


def history_amount_to_satoshis(history):
    """Convert a WalletHistory BCH amount to satoshis, guarding against overflow."""
    if history.amount is None:
        return None
    try:
        sats = int(round(abs(history.amount) * SATOSHIS_PER_BCH))
    except (OverflowError, ValueError):
        return None
    if sats > BIGINT_MAX:
        return None
    return sats


def activity_kind_for_history(history):
    """Map a WalletHistory record to its WalletActivity kind, or None if not tracked."""
    if not history.wallet or history.wallet.wallet_type != 'bch':
        return None
    if history.token and history.token.name.lower() != 'bch':
        return None
    if history.record_type == WalletHistory.OUTGOING:
        return WalletActivity.KIND_TRANSACTION_SEND
    if history.record_type == WalletHistory.INCOMING:
        return WalletActivity.KIND_TRANSACTION_RECEIVE
    return None