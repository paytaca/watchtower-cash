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

    def handle(self, *args, **options):
        txid = options["txid"]
        currency = options["currency"]
        currency = str(currency).upper().strip()

        tx_data = get_tx_with_fiat_amounts(txid, currency=currency)

        print(json.dumps(tx_data, indent=4, default=str))


def get_tx_with_fiat_amounts(txid, currency="PHP"):
    tx = NODE.BCH.get_transaction(txid)

    tx["currency"] = currency
    market_price_filter_kwarg = { f"market_prices__{currency}__isnull": False }
    market_price_field = f"market_prices__{currency}"

    total_input_amount = 0
    total_output_amount = 0

    if currency == "USD":
        market_price_filter_kwarg = { "usd_price__isnull": False}
        market_price_field = "usd_price"

    for vin in tx["inputs"]:
        price = WalletHistory.objects \
            .filter(txid=vin["txid"]) \
            .filter(token__name="bch") \
            .filter(**market_price_filter_kwarg) \
            .values_list(market_price_field, flat=True).first()

        if not price:
            continue

        price = round(Decimal(price), 3)
        sats = Decimal(vin["value"])
        bch = sats / 10 ** 8
        amount = round(bch * price, 3)

        vin["price"] = price
        vin["amount"] = amount

        if amount:
            total_input_amount += amount
    
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

    return tx
