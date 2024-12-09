import json
import math
import decimal
from django.utils import timezone
from django.conf import settings
from django.db.models import Sum, F

from stablehedge.apps import LOGGER
from stablehedge import models
from stablehedge.utils.anyhedge import get_latest_oracle_price

from main import models as main_models

REDIS_STORAGE = settings.REDISKV

def find_fiat_token_utxos(redemptionContractOrAddress, min_token_amount=None, min_satoshis=None):
    if isinstance(redemptionContractOrAddress, str):
        obj = models.RedemptionContract(redemptionContractOrAddress)
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


def get_24hr_volume_sats(redemption_contract_address:str, ttl=60 * 5, force=False):
    volume_24_hr = get_24hr_volume_data(redemption_contract_address, ttl=ttl, force=force)
    LOGGER.debug(f"RedemptionContractTransaction 24 hr volume | {volume_24_hr}")

    total = decimal.Decimal(0)
    if not isinstance(volume_24_hr, dict):
        return

    for value in volume_24_hr.values():
        total += value
    return total


def get_24hr_volume_data(redemption_contract_address:str, ttl=60 * 5, force=False) -> dict:
    REDIS_KEY = f"redemption-contract-24hr-volume-{redemption_contract_address}"

    if not force:
        cached_value = REDIS_STORAGE.get(REDIS_KEY)
        if cached_value:
            try:
                data = json.loads(cached_value)
                parsed_data = {key: decimal.Decimal(val) for key, val in data.items()}
                return parsed_data
            except (TypeError, AttributeError, decimal.InvalidOperation):
                pass

    data = models.RedemptionContractTransaction.objects \
        .filter(
            redemption_contract__address=redemption_contract_address,
            status=models.RedemptionContractTransaction.Status.SUCCESS,
            txid__isnull=False,
            created_at__gte=timezone.now() - timezone.timedelta(seconds=86_400),
        ) \
        .values("id", "utxo", "transaction_type", "price_oracle_message__price_value")

    volume_map = dict(
        inject = decimal.Decimal(0),
        deposit = decimal.Decimal(0),
        redeem = decimal.Decimal(0),
    )
    for record in data:
        tx_type = record["transaction_type"]
        price_value = decimal.Decimal(record["price_oracle_message__price_value"])
        if record["transaction_type"] == models.RedemptionContractTransaction.Type.REDEEM:
            token_amount = decimal.Decimal(record["utxo"]["satoshis"])
            bch = token_amount / price_value
            satoshis = bch * decimal.Decimal(10 ** 8)
        else:
            satoshis = decimal.Decimal(record["utxo"]["satoshis"])
        LOGGER.debug(f"RedemptionContractTransaction #{record['id']} | VALUE | {satoshis} satoshis")

        if not isinstance(volume_map.get(tx_type), decimal.Decimal):
            volume_map[tx_type] = decimal.Decimal(0)

        volume_map[tx_type] += satoshis

    REDIS_STORAGE.set(REDIS_KEY, str(json.dumps(volume_map, default=str)), ex=ttl)
    return volume_map
