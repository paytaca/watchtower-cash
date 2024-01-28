from main.models import WalletHistory, AssetPriceLog, WalletPreferences
from django.db.models import Avg, Sum, F, FloatField
from main.utils.market_price import get_yadio_rate
from decimal import Decimal


def compute_wallet_yield(wallet_hash):
    incoming_txs = WalletHistory.objects.filter(
        wallet__wallet_hash=wallet_hash,
        token__name='bch',
        record_type='incoming',
        usd_price__isnull=False
    )
    
    result = None
    agg_values = incoming_txs.aggregate(Avg('usd_price'), Sum('amount'))

    price_log = AssetPriceLog.objects.filter(
        currency='USD',
        relative_currency='BCH'
    ).latest('id')

    if agg_values and price_log:
        total_bch = agg_values['amount__sum']
        query = incoming_txs.annotate(total_usd=Sum(F('amount') * F('usd_price'), output_field=FloatField())).aggregate(Sum('total_usd'))
        total_usd_worth = query['total_usd__sum']

        current_usd_price = price_log.price_value
        current_usd_worth = Decimal(total_bch) * Decimal(current_usd_price)

        computed_yield = Decimal(current_usd_worth) - Decimal(total_usd_worth)

        wallet_pref = WalletPreferences.objects.get(wallet__wallet_hash=wallet_hash)
        if wallet_pref.selected_currency != 'USD':
            usd_exchange_rate = get_yadio_rate(wallet_pref.selected_currency, 'USD')
            computed_yield = Decimal(usd_exchange_rate['rate']) * computed_yield
        
        result = {
            wallet_pref.selected_currency: round(computed_yield, 2)
        }
    
    return result
