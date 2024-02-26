import json
import requests
import concurrent.futures
from decimal import Decimal
from datetime import timedelta, datetime
from django.db import models
from django.apps import apps
from django.conf import settings
from django.utils import timezone as tz
from main.models import (
    AssetPriceLog,
    WalletHistory,
)


def fetch_currency_value_for_timestamp(timestamp, currency="USD", relative_currency="BCH"):
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
        relative_currency=relative_currency,
        timestamp__gt = timestamp_range_low,
        timestamp__lt = timestamp_range_high,
    ).annotate(
        diff=models.Func(models.F("timestamp"), timestamp, function="GREATEST") - models.Func(models.F("timestamp"), timestamp, function="LEAST")
    ).order_by("diff").first()

    if closest:
        return (closest.price_value, closest.timestamp, closest.source)

    # Anyhedge oracles below are only based on BCH
    if relative_currency != "BCH":
        return None

    try:
        Oracle = apps.get_model("anyhedge", "Oracle")
        PriceOracleMessage = apps.get_model("anyhedge", "PriceOracleMessage")

        oracles = Oracle.objects.filter(asset_currency=currency, active=True)
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

    return None


def get_latest_bch_rates(currencies=[]):
    """
        Fetch latest BCH rates
        Will always return a usd/bch rate

        Returns:
            Map(currency: String, bch_rate: tuple)
                - dictionary of currency to rate
            bch_rate = (price_value: decimal.Decimal, actual_timestamp: datetime.datetime, source: str): tuple
            - price_value: (e.g. USD/BCH)
            - actual_timestamp: the actual timestamp returned from the source
            - source: where the data came from
    """
    asset_prices = []
    currencies = [c.lower() for c in currencies if isinstance(c, str) and len(c)]
    if "usd" not in currencies:
        currencies.append("usd")
    vs_currencies = ",".join(currencies)
    response = requests.get(
        # f"https://api.coingecko.com/api/v3/simple/price/?ids=bitcoin-cash&vs_currencies={vs_currencies}",
        f"https://pro-api.coingecko.com/api/v3/simple/price/?ids=bitcoin-cash&vs_currencies={vs_currencies}",
        timeout=15,
        headers={
            'x-cg-pro-api-key': settings.COINGECKO_API_KEY
        }
    )
    response_timestamp = tz.make_aware(
        datetime.strptime(response.headers["Date"], "%a, %d %b %Y %H:%M:%S %Z")
    )
    response_data = response.json()
    bch_rates = response_data["bitcoin-cash"]

    usd_rate = bch_rates.get("usd", None)
    currencies_to_convert = []
    response = {}
    for currency in currencies:
        if currency in bch_rates:
            response[currency] = (
                Decimal(bch_rates[currency]),
                response_timestamp,
                "coingecko",
            )

            if currency == "ars":
                currencies_to_convert.append(currency)
        else:
            currencies_to_convert.append(currency)

    if usd_rate is not None and len(currencies_to_convert):
        usd_rates_resp = get_yadio_rates(currencies=currencies_to_convert)
        for currency, usd_rate_resp in usd_rates_resp.items():
            if isinstance(usd_rate_resp, dict) and "rate" in usd_rate_resp and "timestamp" in usd_rate_resp:
                price_value = usd_rate_resp["rate"] * usd_rate
                response[currency] = (
                    Decimal(price_value),
                    tz.make_aware(
                        datetime.fromtimestamp(usd_rate_resp["timestamp"] / 1000)
                    ),
                    "coingecko-yadio",
                )

    return response


def get_yadio_rate(currency=None, source_currency="USD"):
    """
    Parameters
        currency: str, source_currency: str
            - rate returned is in currency per source_currency
    Returns:
        {"rate": float, "timestamp": int, "request": str}
    """
    return requests.get(f"https://api.yadio.io/rate/{currency}/{source_currency}", timeout=15).json()


def get_yadio_rates(currencies=[], source_currency="USD"):
    """
    Parameters
        currencies: List(str), source_currency: str
            - rate returned is in currency per source_currency
    Returns:
        Map("currency": str, {"rate": float, "timestamp": int, "request": str})
    """
    with concurrent.futures.ThreadPoolExecutor() as executor:
        threads = {}
        for currency in currencies:
            threads[currency] = executor.submit(
                get_yadio_rate, currency=currency, source_currency=source_currency)

        results = {}
        for currency, thread in threads.items():
            try:
                results[currency] = thread.result()
            except Exception as error:
                results[currency] = error

        return results


def get_and_save_latest_bch_rates(currencies=[], max_age=30):
    assert max_age > 0, "Max age must be positive"
    assert max_age < 60, "Max age must not be more than 60seconds=1minute"
    response = {}
    fresh_rates = AssetPriceLog.objects.filter(
        relative_currency="BCH", currency__in=currencies,
        timestamp__gte=tz.now() - timedelta(seconds=max_age),
    )

    fresh_rate_currencies = fresh_rates.values_list("currency", flat=True).distinct()
    missing_currencies = [currency for currency in currencies if currency not in fresh_rate_currencies]

    bch_rates = get_latest_bch_rates(currencies=missing_currencies)
    for currency in missing_currencies:
        bch_rate = bch_rates.get(currency.lower(), None)
        if not bch_rate: continue
        price_log_data = {
            'currency': currency,
            'relative_currency': "BCH",
            'timestamp': bch_rate[1],
            'source': bch_rate[2]
        }

        price_log_check = AssetPriceLog.objects.filter(**price_log_data)
        if price_log_check.exists():
            price_log_check.update(price_value = bch_rate[0])
            price_log = price_log_check.first()
        else:
            price_log = AssetPriceLog.objects.create(
                **price_log_data, price_value=bch_rate[0],
            )

        response[currency] = price_log

    for price_log in fresh_rates:
        response[price_log.currency] = price_log

    return response


def save_wallet_history_currency(wallet_hash, currency):
    if not currency:
        return

    queryset = WalletHistory.objects.filter(
        wallet__wallet_hash=wallet_hash,
        token__name="bch",
        tx_timestamp__isnull=False,
    )

    if currency == "USD":
        queryset = queryset.filter(models.Q(usd_price__isnull=True) | models.Q(**{f"market_prices__{currency}__isnull": True}))
    else:
        queryset = queryset.filter(**{f"market_prices__{currency}__isnull": True})


    class Epoch(models.expressions.Func):
        template = 'EXTRACT(epoch FROM %(expressions)s)::INTEGER'
        output_field = models.IntegerField()

    WINDOW_SIZE = 60 # we will group wallet history timestamps by windows
    NUM_OF_WINDOWS = 30 # specify a max number of windows to limit the db load

    timestamp_blocks = queryset.annotate(
        ts_epoch = Epoch(models.F("tx_timestamp"))
    ).annotate(
        ts_block = models.F("ts_epoch") - models.F("ts_epoch") % models.Value(WINDOW_SIZE),
    ).order_by("-ts_block").values_list("ts_block", flat=True).distinct()[:NUM_OF_WINDOWS]

    results = []
    for ts_block in timestamp_blocks:
        timestamp_range_low = tz.make_aware(datetime.fromtimestamp(ts_block))
        timestamp = timestamp_range_low + timedelta(seconds=WINDOW_SIZE/2)
        timestamp_range_high = timestamp_range_low + timedelta(seconds=WINDOW_SIZE)

        asset_price_logs = AssetPriceLog.objects.filter(
            currency=currency,
            relative_currency="BCH",
            timestamp__gte = timestamp_range_low,
            timestamp__lte = timestamp_range_high,
        ).annotate(
            diff=models.Func(models.F("timestamp"), timestamp, function="GREATEST") - models.Func(models.F("timestamp"), timestamp, function="LEAST")
        ).order_by("-diff")

        closest = asset_price_logs.first()
        if closest:
            results.append(f"{timestamp} | {closest.price_value} | {currency}")
            queryset_block = queryset.filter(
                tx_timestamp__gte=timestamp_range_low,
                tx_timestamp__lte=timestamp_range_high,
            )
            for wallet_history in queryset_block:
                market_prices = wallet_history.market_prices or {}
                market_prices[currency] = float(closest.price_value)
                wallet_history.market_prices = market_prices
                if currency == "USD" and wallet_history.usd_price is None:
                    wallet_history.usd_price = closest.price_value
                wallet_history.save()

    return results
