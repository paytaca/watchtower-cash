import logging
from django.db import models
from django.db.models import ProtectedError
from main.models import Transaction, WalletHistory

from .cache import (
    clear_cache_for_spent_transactions,
    clear_wallet_balance_cache,
    clear_wallet_history_cache,
)

LOGGER = logging.getLogger(__name__)

# Maximum depth when recursively reverting descendants of a dropped transaction.
MAX_DESCENDANT_DEPTH = 10

# HELPER FUNCTIONS
def mark_transaction_inputs_as_spent(bch_tx):
    """
    See main.utils.queries.bchn.BCHN class,
    param must be from _parse_transaction() or get_transaction()
    """
    LOGGER.info(f"MARKING TRANSACTION INPUTS AS SPENT: {bch_tx['txid']}")

    spent_txs_list = []
    for _input in bch_tx['inputs']:
        spent_txs_list.append((_input['txid'], _input['spent_index']))
    return mark_transactions_as_spent(spent_txs_list, bch_tx['txid'])


def mark_transactions_as_spent(transactions, spending_txid):
    """
    Clear cache and mark transactions as spent.

    Args:
        transactions: List of tuples (txid, index) representing transactions to mark as spent
        spending_txid: The transaction ID that is spending these transactions
    """
    if not transactions: return
    LOGGER.info(f"MARKING TRANSACTIONS AS SPENT: {spending_txid} | {transactions}")

    # Build Q filter for all transactions
    inputs_filter = models.Q()
    for txid, index in transactions:
        inputs_filter = inputs_filter | models.Q(txid=txid, index=index)
    
    transaction_queryset = Transaction.objects.filter(inputs_filter)
    clear_cache_for_spent_transactions(transaction_queryset)
    transaction_queryset.update(spent=True, spending_txid=spending_txid)


def reverse_dropped_transaction(txid, _depth=0):
    """
    Reverse a transaction that was dropped from the mempool (never confirmed).

    This handles the Cauldron "conflicting trades & reversal" case: when a
    conflicting trade wins, the losing trade and everything built on top of it
    are dropped from the mempool. Watchtower marks inputs as spent and records
    outputs as unconfirmed at mempool-sighting time, so those effects must be
    undone when the transaction disappears from both mempool and chain.

    Steps:
      1. Restore inputs this tx marked as spent (spent=False, spending_txid='').
      2. Recursively reverse descendants (txs that spent this tx's outputs).
      3. Delete this tx's phantom unconfirmed output rows.
      4. Delete this tx's WalletHistory rows.
      5. Clear balance/history caches for affected wallets.

    Idempotent and safe to call repeatedly.

    Args:
        txid: transaction id known to no longer exist on the node
        _depth: internal recursion depth guard

    Returns:
        dict summary of what was reversed
    """
    summary = {
        'txid': txid,
        'restored_inputs': 0,
        'deleted_outputs': 0,
        'deleted_history': 0,
        'reverted_children': [],
        'protected_output_ids': [],
    }

    if _depth > MAX_DESCENDANT_DEPTH:
        LOGGER.warning(
            f"reverse_dropped_transaction: max depth reached for {txid}; "
            f"remaining descendants (if any) will be handled by a later sweep"
        )
        return summary

    affected_wallet_hashes = set()

    # 1. Restore the inputs that this tx marked as spent.
    spent_inputs_qs = Transaction.objects.filter(spending_txid=txid, spent=True)
    affected_wallet_hashes.update(
        spent_inputs_qs.filter(address__wallet__isnull=False)
        .values_list('address__wallet__wallet_hash', flat=True)
        .distinct()
    )
    clear_cache_for_spent_transactions(spent_inputs_qs)
    summary['restored_inputs'] = spent_inputs_qs.update(spent=False, spending_txid='')

    # 2. Reverse descendants first, while this tx's output rows still exist to
    #    discover them. A child of a nonexistent tx can never confirm.
    child_txids = list(
        Transaction.objects.filter(txid=txid)
        .exclude(spending_txid='')
        .exclude(spending_txid__isnull=True)
        .values_list('spending_txid', flat=True)
        .distinct()
    )
    for child_txid in child_txids:
        if child_txid == txid:
            continue
        if Transaction.objects.filter(txid=child_txid, blockheight__isnull=False).exists():
            LOGGER.warning(
                f"reverse_dropped_transaction: skipping child {child_txid} of {txid} "
                f"because it has confirmed transactions in the database"
            )
            continue
        child_summary = reverse_dropped_transaction(child_txid, _depth=_depth + 1)
        summary['reverted_children'].append(child_txid)
        summary['restored_inputs'] += child_summary['restored_inputs']
        summary['deleted_outputs'] += child_summary['deleted_outputs']
        summary['deleted_history'] += child_summary['deleted_history']
        summary['reverted_children'] += child_summary['reverted_children']
        summary['protected_output_ids'] += child_summary['protected_output_ids']

    # 3. Delete phantom unconfirmed outputs.
    phantom_outputs_qs = Transaction.objects.filter(txid=txid, blockheight__isnull=True)
    affected_wallet_hashes.update(
        phantom_outputs_qs.filter(address__wallet__isnull=False)
        .values_list('address__wallet__wallet_hash', flat=True)
        .distinct()
    )
    for output_txn in phantom_outputs_qs:
        try:
            output_txn.delete()
            summary['deleted_outputs'] += 1
        except ProtectedError:
            # e.g. paytacapos PROTECT foreign keys; leave the row and log
            summary['protected_output_ids'].append(output_txn.id)
            LOGGER.warning(
                f"reverse_dropped_transaction: could not delete protected output "
                f"Transaction#{output_txn.id} ({txid}:{output_txn.index})"
            )

    # 4. Delete wallet history rows for this tx (it never existed on-chain).
    summary['deleted_history'] += WalletHistory.objects.filter(txid=txid).delete()[0]

    # 5. Clear caches for all affected wallets.
    for wallet_hash in affected_wallet_hashes:
        if wallet_hash:
            clear_wallet_balance_cache(wallet_hash)
            clear_wallet_history_cache(wallet_hash)

    LOGGER.info(f"REVERSED DROPPED TRANSACTION: {summary}")
    return summary
