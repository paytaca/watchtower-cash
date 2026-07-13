from django.core.management.base import BaseCommand

import json
from decimal import Decimal
from django.utils import timezone
from django.db.models import F
from main.models import WalletHistory, Transaction, AssetPriceLog
from main.tasks import NODE

class Command(BaseCommand):
    help = "Get transaction data with fiat amounts of BCH inputs & outputs"

    def add_arguments(self, parser):
        parser.add_argument("-t", "--txid", type=str)
        parser.add_argument("-c", "--currency", type=str, default="PHP")
        parser.add_argument("-a", "--age-threshold-days", type=int, default=30)

    def handle(self, *args, **options):
        txid = options["txid"]
        currency = options["currency"]
        currency = str(currency).upper().strip()
        age_threshold_days = options["age_threshold_days"]

        tx_data = get_tx_with_fiat_amounts(txid, currency=currency, age_threshold_days=age_threshold_days)

        print(json.dumps(tx_data, indent=4, default=str))


def _get_input_timestamp(input_txid):
    tx_timestamp = Transaction.objects \
        .filter(txid=input_txid, tx_timestamp__isnull=False) \
        .values_list("tx_timestamp", flat=True).first()

    if tx_timestamp:
        return tx_timestamp

    wallet_history_timestamp = WalletHistory.objects \
        .filter(txid=input_txid, tx_timestamp__isnull=False) \
        .values_list("tx_timestamp", flat=True).first()

    return wallet_history_timestamp


def _fetch_cashout_price(txid, currency, cashout_timestamp, market_price_filter_kwarg, market_price_field):
    price = WalletHistory.objects \
        .filter(txid=txid) \
        .filter(token__name="bch") \
        .filter(**market_price_filter_kwarg) \
        .values_list(market_price_field, flat=True).first()

    if not price:
        price = AssetPriceLog.objects \
            .filter(currency=currency, relative_currency="BCH") \
            .filter(timestamp__gte=cashout_timestamp - timezone.timedelta(seconds=30*60)) \
            .filter(timestamp__lte=cashout_timestamp + timezone.timedelta(seconds=30*60)) \
            .values_list("price_value", flat=True).first()

    return round(Decimal(price), 3) if price else None


def get_tx_with_fiat_amounts(txid, currency="PHP", age_threshold_days=30):
    tx = NODE.BCH.get_transaction(txid)

    tx["currency"] = currency
    market_price_filter_kwarg = { f"market_prices__{currency}__isnull": False }
    market_price_field = f"market_prices__{currency}"

    total_input_amount = 0
    total_output_amount = 0

    if currency == "USD":
        market_price_filter_kwarg = { "usd_price__isnull": False}
        market_price_field = "usd_price"

    # Resolve cashout timestamp
    cashout_timestamp = Transaction.objects \
        .filter(txid=tx["txid"], tx_timestamp__isnull=False) \
        .values_list("tx_timestamp", flat=True).first()

    if not cashout_timestamp:
        cashout_timestamp = timezone.make_aware(
            timezone.datetime.fromtimestamp(tx["timestamp"])
        )

    # Fetch BCH price at cashout time — this is the reference point for all comparisons
    cashout_price = _fetch_cashout_price(tx["txid"], currency, cashout_timestamp, market_price_filter_kwarg, market_price_field)

    # Fetch today's price for reference display only
    today_price_raw = AssetPriceLog.objects \
        .filter(currency=currency, relative_currency="BCH") \
        .order_by('-timestamp') \
        .values_list("price_value", flat=True).first()
    today_price = round(Decimal(today_price_raw), 3) if today_price_raw else None

    for vin in tx["inputs"]:
        sats = Decimal(vin["value"])
        bch = sats / 10 ** 8

        historical_price = WalletHistory.objects \
            .filter(txid=vin["txid"]) \
            .filter(token__name="bch") \
            .filter(**market_price_filter_kwarg) \
            .values_list(market_price_field, flat=True).first()

        historical_amount = None
        if historical_price:
            historical_price = round(Decimal(historical_price), 3)
            historical_amount = round(bch * historical_price, 3)

        # Determine age of input
        input_timestamp = _get_input_timestamp(vin["txid"])
        age_days = None
        is_old = False
        if input_timestamp and cashout_timestamp:
            age_days = (cashout_timestamp - input_timestamp).days
            is_old = age_days > age_threshold_days

        # Compute cashout amount at the cashout transaction's BCH price
        cashout_amount = None
        if cashout_price:
            cashout_amount = round(bch * cashout_price, 3)

        # Fiat gain/loss: cashout value vs historical value at receipt
        fiat_gain_loss = None
        if cashout_amount is not None and historical_amount is not None:
            fiat_gain_loss = round(cashout_amount - historical_amount, 3)

        vin["historical_price"] = historical_price
        vin["historical_amount"] = historical_amount
        vin["cashout_price"] = cashout_price
        vin["cashout_amount"] = cashout_amount
        vin["today_price"] = today_price
        vin["today_amount"] = round(bch * today_price, 3) if today_price else None
        vin["fiat_gain_loss"] = fiat_gain_loss
        vin["age_days"] = age_days
        vin["is_old"] = is_old

        # Amount used for cost basis: historical (what merchant originally received)
        # Fall back to cashout amount if no historical price data available
        if historical_amount is not None:
            vin["amount"] = historical_amount
        elif cashout_amount is not None:
            vin["amount"] = cashout_amount
        else:
            vin["amount"] = None

        if vin["amount"]:
            total_input_amount += vin["amount"]

    if cashout_price:
        for vout in tx["outputs"]:
            sats = Decimal(vout["value"])
            bch = sats / 10 ** 8
            cashout_amount = round(bch * cashout_price, 3)

            vout["price"] = cashout_price
            vout["amount"] = cashout_amount
            vout["today_price"] = today_price
            vout["today_amount"] = round(bch * today_price, 3) if today_price else None

            total_output_amount += cashout_amount

    tx["total_input_amount"] = total_input_amount
    tx["total_output_amount"] = total_output_amount
    tx["age_threshold_days"] = age_threshold_days
    tx["cashout_timestamp"] = str(cashout_timestamp)
    tx["cashout_price"] = cashout_price

    return tx
