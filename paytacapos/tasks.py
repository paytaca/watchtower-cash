
from celery import shared_task
from rampp2p.models import MarketPrice
from paytacapos.models import CashOutOrder, CashOutTransaction, WalletHistory
from datetime import timedelta
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

@shared_task(queue='paytacapos__cashout')
def calculate_cashout_total (cashout_order_id):
    '''
    Calculates and saves the payout detail of a given CashOutOrder.
    Saves the following info:
        - initial_total:    The total fiat amount of the transactions at the market price when they were created
        - payout_total:     The total fiat amount of the transactions at the current market price
        - loss_gain:        The difference between the payout_total and initial_total 
                            (positive if market price had increased, negative if decreased, zero if there was no change)
        - loss_covered:     The loss amount covered if loss_gain is < 0. This only applies to transactions not older than 30 days.
        - total_bch_amount: The total bch amount of the transactions
    '''

    logger.warning(f'calculate_cashout_total | order id: {cashout_order_id}')
    
    try:
        order = CashOutOrder.objects.get(id=cashout_order_id)
        wallet_history_ids = CashOutTransaction.objects.filter(order__id=order.id).values_list('wallet_history', flat=True)
        txns = WalletHistory.objects.filter(id__in=wallet_history_ids)
        current_market_price = MarketPrice.objects.get(currency=order.currency.symbol)

        initial_total = 0
        payout_total = 0
        loss_gain = 0
        loss_covered = 0
        total_bch_amount = 0
        for tx in txns:
            tx_market_price = tx.market_prices[order.currency.symbol]

            initial_amount = float(tx.amount) * float(tx_market_price)
            payout_amount = float(tx.amount) * float(current_market_price.price)

            initial_total += initial_amount
            payout_total += payout_amount

            thirty_days_ago = timezone.now() - timedelta(days=30)
            is_loss_protected = tx.tx_timestamp >= thirty_days_ago
            if payout_amount < initial_amount and is_loss_protected:
                loss = initial_amount - payout_amount
                loss_covered += loss
            
            total_bch_amount += float(tx.amount)
        loss_gain = payout_total - initial_total
        payout_total += loss_covered

        payout_details = {
            'initial_total': initial_total,
            'payout_total': payout_total,
            'loss_gain': loss_gain,
            'loss_covered': loss_covered,
            'total_bch_amount': total_bch_amount
        }

        order.payout_details = payout_details
        order.payout_amount = payout_total
        order.save()

    except Exception as err:
        logger.exception(err)