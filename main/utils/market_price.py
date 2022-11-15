import requests
from decimal import Decimal
from datetime import timedelta 
from django.db import models
from django.apps import apps
from main.models import AssetPriceLog


def fetch_usd_value(timestamps):
    currency="USD"
    price_values = []
    for timestamp in timestamps:
        data = fetch_currency_value_for_timestamp(timestamp, currency=currency)

def fetch_currency_value_for_timestamp(timestamp, currency="USD"):
    """
    Get currency price with closest timestamp within a +/- 30 seconds margin

    Parameters
        timestamp: datetime.datetime

    Returns:
        (price_value: decimal.Decimal, actual_timestamp: datetime.datetime, source: str): tuple
            - price_value: (e.g. USD/BCH)
            - actual_timestamp: the actual timestamp returned from the source
            - source: where the data came from
    """
    timestamp_range_low = timestamp - timedelta(seconds=30)
    timestamp_range_high = timestamp + timedelta(seconds=30)
    closest = AssetPriceLog.objects.filter(
        currency=currency,
        timestamp__gt = timestamp_range_low,
        timestamp__lt = timestamp_range_high,
    ).annotate(
        diff=models.Func(models.F("timestamp"), timestamp, function="GREATEST") - models.Func(models.F("timestamp"), timestamp, function="LEAST")
    ).order_by("diff").first()

    if closest:
        return (closest.price_value, closest.timestamp, closest.source)

    try:
        Oracle = apps.get_model("anyhedge", "Oracle")
        PriceOracleMessage = apps.get_model("anyhedge", "PriceOracleMessage")

        oracles = Oracle.objects.filter(asset_currency=currency)
        oracles_decimals_map = { oracle.pubkey: oracle.asset_decimals for oracle in oracles }
        closest = PriceOracleMessage.objects.filter(
            pubkey__in=oracles_decimals_map.keys(),
            message_timestamp__gt = timestamp_range_low,
            message_timestamp__lt = timestamp_range_high,
        ).annotate(
            diff=models.Func(models.F("message_timestamp"), timestamp, function="GREATEST") - models.Func(models.F("message_timestamp"), timestamp, function="LEAST")
        ).order_by("diff").first()

        if closest:
            asset_decimals = oracles_decimals_map[closest.pubkey]
            price_value = Decimal(closest.price_value) / 10 ** asset_decimals
            return (price_value, closest.message_timestamp, f"anyhedge:{closest.pubkey}")
    except LookupError:
        pass


    coingecko_resp = requests.get(
        "https://api.coingecko.com/api/v3/coins/bitcoin-cash/market_chart/range?" + \
        "vs_currency=usd" + \
        f"&from={timestamp_range_low.timestamp()}" + \
        f"&to={timestamp_range_high.timestamp()}"
    )
    coingecko_prices_list = coingecko_resp.json().get("prices", [])
    if isinstance(coingecko_prices_list, list):
        sort_element_value = lambda price: abs((timestamp.timestamp() * 1000 - price[0]))
        # sorted price list by timestamp difference from the timestamp returned by data
        sorted_price_list = sorted(coingecko_prices_list, key=sort_element_value)
        if len(sorted_price_list):
            closest = sorted_price_list[0]
            closest_timestamp = datetime.fromtimestamp(closest[0]/1000).replace(tzinfo=pytz.UTC)
            return (Decimal(closest[1]), closest_timestamp, "coingecko")

    return None
