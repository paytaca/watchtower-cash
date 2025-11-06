import logging
from django.db import models
from main.models import Transaction

from .cache import clear_cache_for_spent_transactions

LOGGER = logging.getLogger(__name__)

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
