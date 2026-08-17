from main.models import WalletActivity, WalletHistory


def activity_kind_for_history(history):
    """Map a WalletHistory record to its WalletActivity kind, or None if not tracked."""
    if not history.wallet or history.wallet.wallet_type != 'bch':
        return None
    if history.record_type == WalletHistory.OUTGOING:
        return WalletActivity.KIND_TRANSACTION_SEND
    if history.record_type == WalletHistory.INCOMING:
        return WalletActivity.KIND_TRANSACTION_RECEIVE
    return None