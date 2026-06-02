from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from main.models import AssetPriceLog
from main.utils.market_price import get_latest_bch_rates
import rampp2p.models as models
from rampp2p.utils.websocket import send_market_price

import logging
logger = logging.getLogger(__name__)

@shared_task(queue='rampp2p__marketprices')
def update_market_prices():
    """
    Updates the market prices for subscribed fiat currencies.
    Reads from AssetPriceLog DB cache first (kept warm by fetch_latest_bch_fiat_prices).
    Falls back to CoinGecko for any currencies missing from cache.
    """

    try:
        all_currencies = models.FiatCurrency.objects.all().values_list('symbol', flat=True)
        currencies = [c.upper() for c in all_currencies if c]
        if not currencies:
            return

        now = timezone.now()
        window = timedelta(seconds=60)

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
            logger.warning(
                "DB cache miss for %d currencies: %s, falling back to CoinGecko",
                len(missing), missing,
            )
            try:
                bch_prices = get_latest_bch_rates(missing)
                for currency, data in bch_prices.items():
                    price_value, _, _ = data
                    found[currency.upper()] = price_value
            except Exception as e:
                logger.error("CoinGecko fallback also failed for %s: %s", missing, e)

        for currency, price_value in found.items():
            rate, _ = models.MarketPrice.objects.get_or_create(currency=currency)
            rate.price = price_value
            rate.save()
            send_market_price({'currency': currency, 'price': price_value}, currency)

    except Exception as e:
        logger.error(f"Error updating market prices: {e}")
