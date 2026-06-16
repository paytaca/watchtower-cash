from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from main.models import AssetPriceLog
import rampp2p.models as models
from rampp2p.utils.websocket import send_market_price

import logging
logger = logging.getLogger(__name__)

@shared_task(queue='rampp2p__marketprices')
def update_market_prices():
    """
    Updates the market prices for subscribed fiat currencies.
    Reads from AssetPriceLog DB cache kept warm by fetch_latest_bch_fiat_prices.
    Does NOT call CoinGecko directly — that is the sole responsibility of
    fetch_latest_bch_fiat_prices (runs every 25s on wallet_history_2 queue).
    """

    try:
        all_currencies = models.FiatCurrency.objects.all().values_list('symbol', flat=True)
        currencies = [c.upper() for c in all_currencies if c]
        if not currencies:
            return

        now = timezone.now()
        window = timedelta(seconds=180)

        price_logs = AssetPriceLog.objects.filter(
            currency__in=currencies,
            relative_currency="BCH",
            timestamp__gt=now - window,
            currency_ft_token__isnull=True,
            relative_currency_ft_token__isnull=True,
        ).order_by('currency', '-timestamp').distinct('currency')

        found = {}
        for log in price_logs:
            found[log.currency] = log.price_value

        missing = [c for c in currencies if c not in found]
        if missing:
            logger.warning("Cache miss for %d currencies: %s — skipping until next cycle", len(missing), missing)

        for currency, price_value in found.items():
            rate, _ = models.MarketPrice.objects.get_or_create(currency=currency)
            rate.price = price_value
            rate.save()
            send_market_price({'currency': currency, 'price': price_value}, currency)

    except Exception as e:
        logger.error(f"Error updating market prices: {e}")
