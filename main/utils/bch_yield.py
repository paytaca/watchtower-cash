from main.models import WalletHistory, AssetPriceLog, WalletPreferences
from django.db.models import Avg, Sum, F, FloatField
from main.utils.market_price import get_yadio_rate
from decimal import Decimal


def compute_wallet_yield(wallet_hash):
    """
    Computes the yield of all incoming BCH in a given wallet

    # TODO -- Improvements needed:
    1. We need to track which incoming BCH has been spent and exclude those from the computation
    2. We need to track change outputs from the same wallet, those ones should have the average price of the inputs
    3. We need to refactor UTXO selection for spending so that those BCH acquired at the cheapest price are spent last

    To implement these improvements, it's best to indicate the market price on each UTXO. The price in the wallet history
    record will just be the average from outputs of the transaction that goes to the same wallet.
    """
    result = None
    try:
        wallet_pref = WalletPreferences.objects.get(wallet__wallet_hash=wallet_hash)
    except WalletPreferences.DoesNotExist:
        return result

    incoming_txs = WalletHistory.objects.filter(
        wallet__wallet_hash=wallet_hash,
        token__name='bch',
        record_type='incoming',
        usd_price__isnull=False
    )
    
    agg_values = incoming_txs.aggregate(Avg('usd_price'), Sum('amount'))

    price_log = AssetPriceLog.objects.filter(
        currency='USD',
        relative_currency='BCH'
    ).latest('id')

    if agg_values and price_log:
        total_bch = agg_values['amount__sum']
        if total_bch:
            query = incoming_txs.annotate(total_usd=Sum(F('amount') * F('usd_price'), output_field=FloatField())).aggregate(Sum('total_usd'))
            total_usd_worth = query['total_usd__sum']

            current_usd_price = price_log.price_value
            current_usd_worth = Decimal(total_bch) * Decimal(current_usd_price)

            computed_yield = Decimal(current_usd_worth) - Decimal(total_usd_worth)

            if wallet_pref.selected_currency != 'USD':
                usd_exchange_rate = get_yadio_rate(wallet_pref.selected_currency, 'USD')
                computed_yield = Decimal(usd_exchange_rate['rate']) * computed_yield
            
            result = {
                wallet_pref.selected_currency: round(computed_yield, 2)
            }
    
    return result
