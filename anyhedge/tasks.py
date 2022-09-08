import logging
import pytz
from datetime import datetime
from celery import shared_task
from django.db import models
from .models import (
    Oracle,
    PriceOracleMessage,
)
from .utils.price_oracle import get_price_messages


## CELERY QUEUES
_TASK_TIME_LIMIT = 300 # 5 minutes
_QUEUE_PRICE_ORACLE = "anyhedge__price_oracle"


LOGGER = logging.getLogger(__name__)


@shared_task(queue=_QUEUE_PRICE_ORACLE, time_limit=_TASK_TIME_LIMIT)
def check_new_price_messages():
    pubkeys = Oracle.objects.values_list("pubkey", flat=True).distinct()
    LOGGER.info(f"Updating oracles: {pubkeys}")
    for pubkey in pubkeys:
        check_new_oracle_price_messages.delay(pubkey)


@shared_task(queue=_QUEUE_PRICE_ORACLE, time_limit=_TASK_TIME_LIMIT)
def check_new_oracle_price_messages(oracle_pubkey):
    LOGGER.info(f"Updating prices for oracle: {oracle_pubkey}")
    latest_timestamp = PriceOracleMessage.objects.filter(
        pubkey=oracle_pubkey,
    ).aggregate(
        value = models.Max("message_timestamp"),
    ).get("message_timestamp")

    count = 5
    if latest_timestamp is not None:
        latest_timestamp = round(latest_timestamp)
        # messages are generated per minute, so we can approximate how many messages we will need to be up to date
        count = datetime.now().timestamp() - latest_timestamp
        count = round(count / 60)

        count = max(1, count)
        count = min(count, 50) # setup a hard limit

    price_messages = get_price_messages(oracle_pubkey, min_message_timestamp=latest_timestamp, count=count)
    for price_message in price_messages:
        PriceOracleMessage.objects.update_or_create(
            pubkey = oracle_pubkey,
            signature = price_message["priceMessage"]["signature"],
            message = price_message["priceMessage"]["message"],
            defaults={
                "message_timestamp": datetime.fromtimestamp(price_message["priceData"]["messageTimestamp"]).replace(tzinfo=pytz.UTC),
                "price_value": price_message["priceData"]["priceValue"],
                "price_sequence": price_message["priceData"]["priceSequence"],
                "message_sequence": price_message["priceData"]["messageSequence"],
            }
        )
