from django.utils import timezone

from anyhedge import models as anyhedge_models

def get_latest_oracle_price(oracle_pubkey:str):
    return _get_latest_oracle_price_message.values_list("price_value", flat=True).first()

def get_latest_oracle_price_message(oracle_pubkey:str):
    return _get_latest_oracle_price_message.first()

def _get_latest_oracle_price_message(oracle_pubkey:str):
    return anyhedge_models.PriceOracleMessage.objects.filter(
        pubkey=oracle_pubkey,
        message_timestamp__gte=timezone.now() - timezone.timedelta(minutes=2),
    ).order_by("-message_timestamp")
