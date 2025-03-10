import json
import math
import decimal
from django.utils import timezone
from django.conf import settings
from django.db.models import Sum, Count, F, Q
from django.db.models import DecimalField

from stablehedge.apps import LOGGER
from stablehedge import models
from stablehedge.utils.anyhedge import get_latest_oracle_price

from main import models as main_models

REDIS_STORAGE = settings.REDISKV

def find_fiat_token_utxos(redemptionContractOrAddress, min_token_amount=None, min_satoshis=None):
    if isinstance(redemptionContractOrAddress, str):
        obj = models.RedemptionContract.objects.get(address=redemptionContractOrAddress)
    else:
        obj = redemptionContractOrAddress

    token_category = obj.fiat_token.category
    queryset = main_models.Transaction.objects.filter(
        address__address=obj.address,
        cashtoken_ft__category=token_category,
        spent=False,
    )

    if min_token_amount is not None:
        queryset = queryset.filter(amount__gte=min_token_amount)
    if min_satoshis is not None:
        queryset = queryset.filter(value__gte=min_satoshis)

    return queryset


def get_fiat_token_balances(wallet_hash:str, with_satoshis=False):
    redemption_contract_data_qs = models.RedemptionContract.objects \
        .values("fiat_token__category", "fiat_token__decimals", "fiat_token__currency", "price_oracle_pubkey") \
        .distinct()

    token_oracle_map = {}
    token_decimals_map = {}
    token_currency_map = {}
    for redemption_contract_data in redemption_contract_data_qs:
        token_category = redemption_contract_data["fiat_token__category"]
        oracle_pubkey = redemption_contract_data["price_oracle_pubkey"]
        decimals = redemption_contract_data["fiat_token__decimals"]
        currency = redemption_contract_data["fiat_token__currency"]
        token_oracle_map[token_category] = oracle_pubkey
        token_decimals_map[token_category] = decimals
        token_currency_map[token_category] = currency


    fiat_token_categories = list(token_oracle_map.keys())

    token_balances = main_models.Transaction.objects \
        .filter(cashtoken_ft__category__in=fiat_token_categories) \
        .filter(wallet__wallet_hash=wallet_hash) \
        .filter(spent=False) \
        .annotate(category=F("cashtoken_ft__category")) \
        .values("category") \
        .order_by("category") \
        .annotate(total_amount = Sum("amount")) \
        .values("category", "total_amount")

    for data in token_balances:
        data["currency"] = token_currency_map.get(data["category"])

    if not with_satoshis:
        return token_balances

    for data in token_balances:
        oracle_pubkey = token_oracle_map.get(data["category"])
        decimals = token_decimals_map.get(data["category"]) or 0

        if not oracle_pubkey:
            continue

        latest_price = get_latest_oracle_price(oracle_pubkey)

        if not latest_price:
            continue

        redeemable = data["total_amount"] / latest_price
        redeemable = math.floor(redeemable)

        data["current_price"] = latest_price
        data["redeemable_satoshis"] = redeemable 

    return token_balances

def get_24hr_volume_data(redemption_contract_address:str, ttl=60 * 5, force=False):
    return get_volume_data(
        redemption_contract_address,
        filter_args=[Q(created_at__gte=timezone.now() - timezone.timedelta(seconds=86_400))],
        cache_key="24hr", ttl=ttl, force=force,
    )

def get_lifetime_volume_data(redemption_contract_address:str, ttl=60*5, force=False):
    return get_volume_data(
        redemption_contract_address, filter_args=[],
        cache_key="lifetime", ttl=ttl, force=force,
    )

def get_volume_data(
    redemption_contract_address:str,
    filter_args:list=[],
    cache_key:str="",
    ttl:int=60*5,
    force=False,
):
    REDIS_KEY = f"redemption-contract-volume:{redemption_contract_address}:{cache_key}"

    if not force:
        cached_value = REDIS_STORAGE.get(REDIS_KEY)
        if cached_value:
            LOGGER.debug(f"Cached volume data | {REDIS_KEY} | {cached_value}")
            try:
                data = json.loads(cached_value)
                for index, record in enumerate(data):
                    data[index]["satoshis"] = decimal.Decimal(record["satoshis"])
                    data[index]["count"] = int(record["count"])
                return data
            except (TypeError, AttributeError, decimal.InvalidOperation) as exception:
                LOGGER.exception(exception)

    data = models.RedemptionContractTransaction.objects \
        .filter(
            *filter_args,
            redemption_contract__address=redemption_contract_address,
            status=models.RedemptionContractTransaction.Status.SUCCESS,
            txid__isnull=False,
        ) \
        .values("transaction_type") \
        .annotate(
            satoshis=Sum(
                "trade_size_in_satoshis",
                output_field=DecimalField(max_digits=15, decimal_places=0)
            ),
            count=Count("id"),
        ) \
        .values("transaction_type", "satoshis", "count").distinct()

    parsed_data = [*data]
    REDIS_STORAGE.set(REDIS_KEY, str(json.dumps(parsed_data, default=str)), ex=ttl)
    return parsed_data
