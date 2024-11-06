import math
from django.db.models import Sum, F

from stablehedge import models

from main import models as main_models

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


def get_fiat_token_balances(wallet_hash:str):
    redemption_contract_data_qs = models.RedemptionContract.objects \
        .values("fiat_token__category", "fiat_token__decimals", "price_oracle_pubkey") \
        .distinct()

    token_oracle_map = {}
    token_decimals_map = {}
    for redemption_contract_data in redemption_contract_data_qs:
        token_category = redemption_contract_data["fiat_token__category"]
        oracle_pubkey = redemption_contract_data["price_oracle_pubkey"]
        decimals = redemption_contract_data["fiat_token__decimals"]
        token_oracle_map[token_category] = oracle_pubkey
        token_decimals_map[token_category] = decimals


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

    from .anyhedge import get_latest_oracle_price

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
