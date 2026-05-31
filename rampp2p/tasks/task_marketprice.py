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
    Reads from AssetPriceLog DB cache (kept warm by fetch_latest_bch_fiat_prices beat task).
    """

    try:
        currencies = models.FiatCurrency.objects.all().values_list('symbol', flat=True)
        now = timezone.now()
        window = timedelta(seconds=30)

        for currency in currencies:
            currency = currency.upper()
            log = AssetPriceLog.objects.filter(
                currency=currency,
                relative_currency="BCH",
                timestamp__gt=now - window,
                timestamp__lte=now + window,
                currency_ft_token__isnull=True,
                relative_currency_ft_token__isnull=True,
            ).order_by("-timestamp").first()

            if not log:
                continue

            rate, _ = models.MarketPrice.objects.get_or_create(currency=currency)
            rate.price = log.price_value
            rate.save()

            data = {'currency': currency, 'price': log.price_value}
            send_market_price(data, currency)

    except Exception as e:
        logger.error(f"Error updating market prices: {e}")
