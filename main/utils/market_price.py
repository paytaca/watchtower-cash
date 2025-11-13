import json
import logging
import requests
import time
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
    CashFungibleToken,
)
LOGGER = logging.getLogger(__name__)


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
            if currency == "ars":
                currencies_to_convert.append(currency)
            else:
                response[currency] = (
                    Decimal(bch_rates[currency]),
                    response_timestamp,
                    "coingecko",
                )
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
    
    # Check if we have a recent price log (less than 10 seconds old)
    ten_seconds_ago = tz.now() - timedelta(seconds=10)
    latest_price_log = AssetPriceLog.objects.filter(
        currency=currency.upper(),
        relative_currency=source_currency.upper(),
        timestamp__gte=ten_seconds_ago
    ).order_by('-timestamp').first()
    
    if latest_price_log:
        # Return cached data from the latest price log
        return {
            "rate": float(latest_price_log.price_value),
            "timestamp": int(latest_price_log.timestamp.timestamp() * 1000),
            "request": f"cached:{latest_price_log.source}"
        }
    
    # If no recent data, make the API request
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
    assert max_age <= 300, "Max age must not be more than 60seconds=1minute"
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

    # Updated to handle both BCH and CashToken FT transactions
    queryset = WalletHistory.objects.filter(
        wallet__wallet_hash=wallet_hash,
        tx_timestamp__isnull=False,
    ).filter(
        models.Q(token__name="bch") | models.Q(cashtoken_ft__isnull=False)
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
        ).order_by("diff")

        closest = asset_price_logs.first()
        
        # If no price found in the time window, try to find the closest one
        if not closest:
            closest = AssetPriceLog.objects.filter(
                currency=currency,
                relative_currency="BCH",
            ).annotate(
                diff=models.Func(models.F("timestamp"), timestamp, function="GREATEST") - models.Func(models.F("timestamp"), timestamp, function="LEAST")
            ).order_by("diff").first()
        if closest:
            results.append(f"{timestamp} | {closest.price_value} | {currency}")
            queryset_block = queryset.filter(
                tx_timestamp__gte=timestamp_range_low,
                tx_timestamp__lte=timestamp_range_high,
            )
            for wallet_history in queryset_block:
                market_prices = wallet_history.market_prices or {}
                
                # For BCH transactions, use the price directly
                # For token transactions, need to convert via token/BCH rate
                price_for_asset = float(closest.price_value)
                
                if wallet_history.cashtoken_ft:
                    # This is a token transaction, need to get token/BCH rate
                    ft_bch_log = get_ft_bch_price_log(
                        wallet_history.cashtoken_ft.category,
                        timestamp=wallet_history.tx_timestamp
                    )
                    if ft_bch_log:
                        # closest.price_value is fiat/BCH
                        # ft_bch_log.price_value is tokens/BCH
                        # We need fiat/token = (fiat/BCH) / (tokens/BCH)
                        price_for_asset = float(closest.price_value / ft_bch_log.price_value)
                
                market_prices[currency] = price_for_asset
                wallet_history.market_prices = market_prices
                if currency == "USD" and wallet_history.usd_price is None:
                    wallet_history.usd_price = price_for_asset
                wallet_history.save()

    return results


class CoingeckoAPI:
    REQUIRED_YADIO_RATE = ["ars"]

    class CoingeckoAPIError(Exception):
        pass

    def __init__(self, pro_api_key=settings.COINGECKO_API_KEY):
        self.pro_api_key = pro_api_key

    @classmethod
    def coin_id_to_asset_name(cls, value) -> str:
        if isinstance(value, bytes):
            value = value.decode()
        if value == "bitcoin-cash": return "BCH"
        return value

    @classmethod
    def asset_name_to_coin_id(cls, value) -> str:
        if isinstance(value, bytes):
            value = value.decode()

        if value == "BCH": return "bitcoin-cash"
        return value

    @classmethod
    def parse_currency(cls, value) -> str:
        if isinstance(value, bytes):
            value = value.decode()
        return value.strip().lower()

    def get_market_prices(self, currencies=["USD"], coin_ids=["bitcoin-cash"], save=False):
        vs_currencies = []
        use_yadio_rates = []
        for c in currencies:
            currency = self.parse_currency(c)
            if not currency: continue

            if currency in self.REQUIRED_YADIO_RATE:
                use_yadio_rates.append(currency)
            else:
                vs_currencies.append(currency)

        if use_yadio_rates and "usd" not in vs_currencies:
            vs_currencies.append("usd")

        coin_ids = [self.asset_name_to_coin_id(coin_id) for coin_id in coin_ids]
        params = dict(vs_currencies=",".join(vs_currencies), ids=",".join(coin_ids))
        if self.pro_api_key: url = "https://pro-api.coingecko.com/api/v3/simple/price/"
        else: url = "https://api.coingecko.com/api/v3/simple/price/"
        response = requests.get(url,
            headers={'x-cg-pro-api-key': self.pro_api_key},
            params=params,
            timeout=15,
        )

        response_timestamp = tz.make_aware(
            datetime.strptime(response.headers["Date"], "%a, %d %b %Y %H:%M:%S %Z")
        )
        response_data = response.json()
        if "error" in response_data: raise CoingeckoAPIError(response_data)

        result = {}
        coin_id_usd_rates = {}
        for coin_id in coin_ids:
            rates_per_currency = response_data.get(coin_id)
            if not rates_per_currency: continue

            result_rates = {}
            for currency in vs_currencies:
                if currency not in rates_per_currency: continue
                price_data = {
                    'currency': currency.upper(),
                    'relative_currency': self.coin_id_to_asset_name(coin_id),
                    'timestamp': response_timestamp,
                    'source': "coingecko",
                    'price_value': round(Decimal(rates_per_currency[currency]), 3),
                }
                result_rates[currency.upper()] = price_data
                if currency == "usd": coin_id_usd_rates[coin_id] = price_data

            if result_rates: result[coin_id] = result_rates

        if use_yadio_rates and len(coin_id_usd_rates.keys()):
            usd_rates_resp = get_yadio_rates(currencies=use_yadio_rates, source_currency="USD")
            for currency, usd_rate_resp in usd_rates_resp.items():
                if not isinstance(usd_rate_resp, dict): continue
                if "rate" not in usd_rate_resp: continue
                if "timestamp" not in usd_rate_resp: continue

                yadio_rate_timestamp = tz.make_aware(
                    datetime.fromtimestamp(usd_rate_resp["timestamp"] / 1000)
                )

                currency_usd_rate = Decimal(usd_rate_resp["rate"])
                for coin_id, price_data in coin_id_usd_rates.items():
                    coin_usd_rate = price_data["price_value"]

                    new_price_data = {**price_data}
                    new_price_data["currency"] = currency.upper()
                    new_price_data["price_value"] = round(currency_usd_rate * coin_usd_rate, 3)
                    new_price_data["source"] = "coingecko-yadio"
                    new_price_data["timestamp"] = max(
                        yadio_rate_timestamp,
                        new_price_data["timestamp"],
                    )

                    result[coin_id][currency.upper()] = new_price_data

        if save:
            for coin_rates in result.values():
                for price_data in coin_rates.values():
                    kwargs = {
                        "currency": price_data["currency"],
                        "relative_currency": price_data["relative_currency"],
                        "source": price_data["source"],
                    }
                    existing_similar_records = AssetPriceLog.objects.filter(
                        **kwargs,
                        timestamp__gte=price_data["timestamp"]-timedelta(seconds=30),
                        timestamp__lte=price_data["timestamp"]+timedelta(seconds=15),
                    )
                    if existing_similar_records.exists():
                        existing_similar_records.update(
                            price_value=price_data["price_value"],
                            timestamp=price_data["timestamp"],
                        )
                        price_data["id"] = existing_similar_records.values_list("id", flat=True).first()
                    else:
                        asset_price_log = AssetPriceLog.objects.create(
                            **kwargs,
                            price_value=price_data["price_value"],
                            timestamp=price_data["timestamp"],
                        )
                        price_data["id"] = asset_price_log.id

        return result


def get_ft_bch_price_log(ft_category:str, timestamp=None):
    relative_currency = "BCH"

    if not timestamp:
        timestamp = tz.now()

    timestamp_range_low = timestamp - timedelta(seconds=30)
    timestamp_range_high = timestamp + timedelta(seconds=30)

    asset_price_log = AssetPriceLog.objects.filter(
        timestamp__gt=timestamp_range_low,
        timestamp__lt=timestamp_range_high,
        currency_ft_token_id=ft_category,
        relative_currency=relative_currency,
    ).annotate(
        diff=models.Func(models.F("timestamp"), timestamp, function="GREATEST") - models.Func(models.F("timestamp"), timestamp, function="LEAST")
    ).order_by("diff").first()

    if asset_price_log:
        return asset_price_log

    ts = int(timestamp.timestamp())
    try:
        response = requests.get(
            f"https://indexer.cauldron.quest/cauldron/price/{ft_category}/at/{ts}",
            timeout=15,
        )
    except Exception as err:
        LOGGER.error(f"Error requesting FT price from cauldron: {err}")
        return None

    if not response.ok:
        LOGGER.error(
            f"Non-200 response from cauldron ({response.status_code}) for {ft_category} @ {ts}: "
            f"{response.text[:200]}"
        )
        return None

    try:
        data = response.json()
    except Exception as err:
        LOGGER.error(
            f"Invalid JSON from cauldron for {ft_category} @ {ts}: {err}; body: {response.text[:200]}"
        )
        return None
    if "price" not in data or "timestamp" not in data:
        return None

    ts_obj = tz.datetime.fromtimestamp(data["timestamp"]).replace(tzinfo=tz.pytz.UTC)
    price__sats_per_token_unit = Decimal(data["price"]) # this is in sats per token unit
    price__bch_per_token_unit = price__sats_per_token_unit / Decimal(10 ** 8)

    ft_token_obj, _ = CashFungibleToken.objects.get_or_create(category=ft_category)
    
    # Force fetch metadata with retries if it's missing
    # This is critical for accurate price calculations - incorrect decimals can cause payment errors
    max_retries = 3
    retry_delay = 0.5  # Start with 0.5 seconds
    
    for attempt in range(max_retries):
        # Refresh from DB to get latest info
        ft_token_obj.refresh_from_db()
        
        if ft_token_obj.info and ft_token_obj.info.decimals is not None:
            # Metadata exists and has decimals, we're good
            break
        
        # Metadata missing, try to fetch it
        if attempt < max_retries - 1:
            LOGGER.warning(
                f"Token {ft_category} metadata missing (attempt {attempt + 1}/{max_retries}). "
                f"Force fetching metadata..."
            )
            ft_token_obj.fetch_metadata()
            # Wait before checking again (exponential backoff)
            time.sleep(retry_delay)
            retry_delay *= 2  # Exponential backoff: 0.5s, 1s, 2s
        else:
            # Final attempt failed
            LOGGER.error(
                f"CRITICAL: Token {ft_category} has no metadata info after {max_retries} attempts. "
                f"Cannot calculate price safely without decimals. Returning None to prevent payment errors."
            )
            return None
    
    # Final check after retries
    ft_token_obj.refresh_from_db()
    if not ft_token_obj.info:
        LOGGER.error(
            f"CRITICAL: Token {ft_category} metadata still missing after retries. "
            f"Returning None to prevent payment errors."
        )
        return None
    
    if ft_token_obj.info.decimals is None:
        LOGGER.error(
            f"CRITICAL: Token {ft_category} metadata missing decimals field. "
            f"Cannot calculate price safely. Returning None to prevent payment errors."
        )
        return None
    
    if not ft_token_obj.info.symbol:
        LOGGER.warning(
            f"Token {ft_category} has no symbol in metadata. "
            f"Using category hash as fallback for display only."
        )
        currency_symbol = ft_category[:8]
    else:
        currency_symbol = ft_token_obj.info.symbol
    
    decimals = ft_token_obj.info.decimals
    price__bch_per_amount = price__bch_per_token_unit * 10 ** decimals
    price_amount_per_bch = 1 / price__bch_per_amount

    price_obj, _ = AssetPriceLog.objects.update_or_create(
        relative_currency=relative_currency,
        timestamp=ts_obj,
        source="cauldron",
        currency_ft_token=ft_token_obj,
        defaults=dict(
            currency=currency_symbol,
            price_value=price_amount_per_bch,
        )
    )
    return price_obj