from django.utils import timezone

from stablehedge import models

from anyhedge import models as anyhedge_models

def get_latest_oracle_price(oracle_pubkey:str):
    return get_latest_oracle_price_messages([oracle_pubkey]).values_list("price_value", flat=True).first()

def get_latest_oracle_price_message(oracle_pubkey:str):
    return get_latest_oracle_price_messages([oracle_pubkey]).first()

def get_latest_oracle_price_messages(oracle_pubkeys:list):
    return anyhedge_models.PriceOracleMessage.objects.filter(
        pubkey__in=oracle_pubkeys,
        message_timestamp__gte=timezone.now() - timezone.timedelta(minutes=2),
    ).order_by("-message_timestamp")


def get_fiat_token_prices(token_categories:list):
    queryset = models.RedemptionContract.objects.filter(
        fiat_token__category__in=token_categories,
    ).values(
        "fiat_token__category", "price_oracle_pubkey", "fiat_token__currency",
    ).distinct()

    results = []
    for data in queryset:
        category = data["fiat_token__category"]
        currency = data["fiat_token__currency"]
        pubkey = data["price_oracle_pubkey"]
        price_message = get_latest_oracle_price_message(pubkey)
        results.append(dict(
            category=category,
            price=price_message.price_value,
            currency=currency,
            timestamp=price_message.message_timestamp
        ))

    return results
