
from celery import shared_task
from main.models import WalletHistory
from paytacapos.models import CashOutOrder, CashOutTransaction 
from datetime import timedelta
from django.utils import timezone
from django.core.exceptions import ValidationError

from rampp2p.models import MarketPrice
from rampp2p.utils import bch_to_satoshi, bch_to_fiat
from main.models import Transaction
from .serializers import BaseCashOutTransactionSerializer

import logging
logger = logging.getLogger(__name__)

def is_loss_protected(timestamp):
    return timestamp >= timezone.now() - timedelta(days=30)

@shared_task(queue='paytacapos__cashout')
def process_cashout_input_txns(order_id, wallet_hash, txids):
    '''
    Processes txids to save as incoming CashOutTransaction for a CashOutOrder, then calculates and saves the 
    total payout details.
    '''
    order = CashOutOrder.objects.get(id=order_id, wallet__wallet_hash=wallet_hash)

    # limit to process only max 500 txids
    if len(txids) > 500:
        raise ValidationError('cannot process more than 500 txids per order')

    initial_total = 0
    payout_total = 0
    loss_covered = 0
    total_bch_amount = 0
    
    for txid in txids:
        txn = Transaction.objects.filter(txid=txid, wallet__wallet_hash=wallet_hash)
        wallet_history = WalletHistory.objects.filter(txid=txid, wallet__wallet_hash=wallet_hash, token__name="bch")

        data = { 
            'order': order.id,
            'txid': txid,
            'record_type': CashOutTransaction.INCOMING
        }

        if txn.exists():
            data['transaction'] = txn.first().id
        
        if wallet_history.exists():
            wallet_history = wallet_history.first()
            data['wallet_history'] = wallet_history.id
        
        serializer = BaseCashOutTransactionSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
        else:
            logger.warning(serializer.errors)

        # calculate payout details
        if wallet_history:
            result = calculate_cashout_details(wallet_history, order.currency.symbol)
            initial_total += result['initial_amount']
            payout_total += result['payout_amount']
            loss_covered += result['loss_covered']
            total_bch_amount += result['bch_amount']

    save_cashout_details(
        order = order,
        total_bch_amount = total_bch_amount,
        initial_total = initial_total,
        loss_covered = loss_covered,
        payout_total = payout_total
    )

def save_cashout_details(**kwargs):
    '''
    Calculates the total payout details and saves it to the CashOutOrder.
    Saves the following info:
        - initial_total:    The total fiat amount of the transactions at the market price when they were created
        - payout_total:     The total fiat amount of the transactions at the current market price
        - loss_gain:        The difference between the payout_total and initial_total 
                            (positive if market price had increased, negative if decreased, zero if there was no change)
        - loss_covered:     The loss amount covered if loss_gain is < 0. This only applies to transactions not older than 30 days.
        - total_bch_amount: The total bch amount of the transactions
    '''

    order = kwargs.get('order')
    total_bch_amount = kwargs.get('total_bch_amount', 0)
    initial_total = kwargs.get('initial_total', 0)
    loss_covered = kwargs.get('loss_covered', 0)
    payout_total = kwargs.get('payout_total', 0)

    sats_amount = bch_to_satoshi(total_bch_amount)
    loss_gain = payout_total - initial_total
    payout_total += loss_covered

    payout_details = {
        'initial_total': str(initial_total),
        'payout_total': str(payout_total),
        'loss_gain': str(loss_gain),
        'loss_covered': str(loss_covered),
        'total_bch_amount': str(total_bch_amount)
    }

    order.payout_details = payout_details
    order.payout_amount = payout_total
    order.sats_amount = sats_amount
    order.save()

def calculate_cashout_details(tx, currency):
    current_market_price = MarketPrice.objects.get(currency=currency)
    tx_market_price = tx.market_prices[currency] # could KeyError

    loss_covered = 0
    initial_amount = bch_to_fiat(tx.amount, tx_market_price)
    payout_amount = bch_to_fiat(tx.amount, current_market_price.price)

    if payout_amount < initial_amount and is_loss_protected(tx.tx_timestamp):
        loss_covered = initial_amount - payout_amount
    
    bch_amount = float(tx.amount)

    return {
        'initial_amount': initial_amount,
        'payout_amount': payout_amount,
        'loss_covered': loss_covered,
        'bch_amount': bch_amount
    }