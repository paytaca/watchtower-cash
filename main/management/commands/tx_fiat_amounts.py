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
    """Resolve the timestamp for an input transaction."""
    tx_timestamp = Transaction.objects \
        .filter(txid=input_txid, tx_timestamp__isnull=False) \
        .values_list("tx_timestamp", flat=True).first()

    if tx_timestamp:
        return tx_timestamp

    wallet_history_timestamp = WalletHistory.objects \
        .filter(txid=input_txid, tx_timestamp__isnull=False) \
        .values_list("tx_timestamp", flat=True).first()

    return wallet_history_timestamp


def _get_current_price(currency):
    """Fetch the latest market price from AssetPriceLog."""
    return AssetPriceLog.objects \
        .filter(currency=currency, relative_currency="BCH") \
        .order_by('-timestamp') \
        .values_list("price_value", flat=True).first()


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

    # Fetch current price for old inputs
    current_price_raw = _get_current_price(currency)
    current_price = round(Decimal(current_price_raw), 3) if current_price_raw else None

    for vin in tx["inputs"]:
        historical_price = WalletHistory.objects \
            .filter(txid=vin["txid"]) \
            .filter(token__name="bch") \
            .filter(**market_price_filter_kwarg) \
            .values_list(market_price_field, flat=True).first()

        if not historical_price:
            continue

        historical_price = round(Decimal(historical_price), 3)
        sats = Decimal(vin["value"])
        bch = sats / 10 ** 8
        historical_amount = round(bch * historical_price, 3)

        # Determine age of input
        input_timestamp = _get_input_timestamp(vin["txid"])
        age_days = None
        is_old = False
        if input_timestamp and cashout_timestamp:
            age_days = (cashout_timestamp - input_timestamp).days
            is_old = age_days > age_threshold_days

        # Compute current amount for old inputs
        current_amount = None
        if is_old and current_price:
            current_amount = round(bch * current_price, 3)

        vin["historical_price"] = historical_price
        vin["historical_amount"] = historical_amount
        vin["current_price"] = current_price if is_old else None
        vin["current_amount"] = current_amount if is_old else None
        vin["age_days"] = age_days
        vin["is_old"] = is_old

        # Use current amount for old inputs, historical for others
        if is_old and current_amount is not None:
            vin["amount"] = current_amount
        else:
            vin["amount"] = historical_amount

        if vin["amount"]:
            total_input_amount += vin["amount"]

    price = WalletHistory.objects \
        .filter(txid=tx["txid"]) \
        .filter(token__name="bch") \
        .filter(**market_price_filter_kwarg) \
        .values_list(market_price_field, flat=True).first()

    if not price:
        tx_timestamp = Transaction.objects \
            .filter(txid=tx["txid"], tx_timestamp__isnull=False) \
            .values_list("tx_timestamp", flat=True).first()

        if not tx_timestamp:
            tx_timestamp = timezone.make_aware(
                timezone.datetime.fromtimestamp(tx["timestamp"])
            )
            price = AssetPriceLog.objects \
                .filter(currency=currency, relative_currency="BCH") \
                .filter(timestamp__gte=tx_timestamp - timezone.timedelta(seconds=30*60)) \
                .filter(timestamp__lte=tx_timestamp + timezone.timedelta(seconds=30*60)) \
                .values_list("price_value", flat=True).first()

    if price:
        for vout in tx["outputs"]:
            price = round(Decimal(price), 3)
            sats = Decimal(vout["value"])
            bch = sats / 10 ** 8
            amount = round(bch * price, 3)

            vout["price"] = price
            vout["amount"] = amount

            if amount:
                total_output_amount += amount

    tx["total_input_amount"] = total_input_amount
    tx["total_output_amount"] = total_output_amount
    tx["age_threshold_days"] = age_threshold_days
    tx["cashout_timestamp"] = str(cashout_timestamp)
    tx["current_price"] = current_price

    return tx
