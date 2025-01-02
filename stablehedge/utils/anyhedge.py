from django.utils import timezone

from stablehedge import models

from anyhedge import models as anyhedge_models

def get_latest_oracle_price(oracle_pubkey:str, max_age:int=120):
    return get_latest_oracle_price_messages([oracle_pubkey], max_age=max_age) \
            .values_list("price_value", flat=True).first()

def get_latest_oracle_price_message(oracle_pubkey:str, max_age:int=120):
    return get_latest_oracle_price_messages([oracle_pubkey], max_age=max_age) \
            .first()

def get_latest_oracle_price_messages(oracle_pubkeys:list, max_age:int=120):
    return anyhedge_models.PriceOracleMessage.objects.filter(
        pubkey__in=oracle_pubkeys,
        message_timestamp__gte=timezone.now() - timezone.timedelta(seconds=max_age),
    ).order_by("-message_timestamp")

def get_fiat_token_price_messages(token_categories:list, max_age:int=60):
    queryset = models.RedemptionContract.objects.filter(
        fiat_token__category__in=token_categories,
    ).values(
        "fiat_token__category", "price_oracle_pubkey", "fiat_token__currency", "fiat_token__decimals",
    ).distinct()

    results = []
    for data in queryset:
        category = data["fiat_token__category"]
        currency = data["fiat_token__currency"]
        decimals = data["fiat_token__decimals"]
        pubkey = data["price_oracle_pubkey"]
        price_message = get_latest_oracle_price_message(pubkey, max_age=max_age)
        results.append(dict(
            category=category,
            currency=currency,
            decimals=decimals,
            price_message=price_message,
        ))

    return results
