from celery import shared_task
import requests
from decimal import Decimal

from rampp2p.utils.websocket import send_market_price
import rampp2p.models as models

import logging
logger = logging.getLogger(__name__)

@shared_task(queue='rampp2p__market_rates')
def update_market_rates():
    # get subscribed fiat currencies
    currencies = models.FiatCurrency.objects.all().values_list('symbol', flat=True)

    # get market prices from coingecko
    market_prices = get_latest_bch_prices_coingecko(currencies)
    result_keys = [e.upper() for e in list(market_prices.keys())]

    # get missing market prices from fullstack.cash
    if len(result_keys) < len(currencies):
        mcurrencies = list(set(currencies) - set(result_keys))
        market_prices_fullstackcash = get_latest_bch_prices_fullstackcash(mcurrencies)
        market_prices.update(market_prices_fullstackcash)

    for currency in market_prices:
        price = market_prices.get(currency)
        if price:
            rate, _ = models.MarketRate.objects.get_or_create(currency=currency.upper())
            rate.price = price
            rate.save()
        data =  { 'currency': currency, 'price' : price }
        send_market_price(data, currency)

def get_latest_bch_prices_coingecko(currencies):
    coin_id = "bitcoin-cash"
    query = { "ids": coin_id, "vs_currencies": ','.join(currencies) }
    response = requests.get("https://api.coingecko.com/api/v3/simple/price/", params=query)
    data = response.json()
    return data.get(coin_id)

def get_latest_bch_prices_fullstackcash(currencies):
    response = requests.get("https://api.fullstack.cash/v5/price/rates")
    data = response.json()

    rates = {}
    for currency in currencies:
        price = data.get(currency)
        if price:
            rates[currency] = Decimal(price)
    return rates
