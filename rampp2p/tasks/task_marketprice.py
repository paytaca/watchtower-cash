from celery import shared_task
from rampp2p.utils.websocket import send_market_price
from main.utils.market_price import get_latest_bch_rates
import rampp2p.models as models
import logging
logger = logging.getLogger(__name__)

@shared_task(queue='rampp2p__marketprices')
def update_market_prices():
    """
    Updates the market prices for subscribed fiat currencies.
    """

    try:
        currencies = models.FiatCurrency.objects.all().values_list('symbol', flat=True)
        bch_prices = get_latest_bch_rates(currencies)

        for currency, data in bch_prices.items():
            price_value, _, _ = data
            
            rate, _ = models.MarketPrice.objects.get_or_create(currency=currency.upper())
            rate.price = price_value
            rate.save()

            data =  { 'currency': currency, 'price' : price_value }
            send_market_price(data, currency)
            
    except Exception as e:
        logger.error(f"Error updating market prices: {e}")
