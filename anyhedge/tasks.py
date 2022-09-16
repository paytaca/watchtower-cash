import logging
import pytz
from datetime import datetime
from celery import shared_task
from django.db import models
from django.utils import timezone
from .models import (
    HedgePosition,
    HedgeSettlement,
    Oracle,
    PriceOracleMessage,
)
from .utils.contract import get_contract_status
from .utils.price_oracle import get_price_messages, parse_oracle_message
from .utils.websocket import send_settlement_update


## CELERY QUEUES
_TASK_TIME_LIMIT = 300 # 5 minutes
_QUEUE_PRICE_ORACLE = "anyhedge__price_oracle"
_QUEUE_SETTLEMENT_UPDATE = "anyhedge__settlement_updates"


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
        latest_timestamp = models.Max("message_timestamp"),
    ).get("latest_timestamp")

    count = 5
    if latest_timestamp is not None:
        latest_timestamp = datetime.timestamp(latest_timestamp)
        latest_timestamp = round(latest_timestamp)
        # messages are generated per minute, so we can approximate how many messages we will need to be up to date
        count = datetime.now().timestamp() - latest_timestamp
        count = round(count / 60)

        count = max(1, count)
        count = min(count, 10) # setup a hard limit

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


@shared_task(queue=_QUEUE_SETTLEMENT_UPDATE, time_limit=_TASK_TIME_LIMIT)
def update_matured_contracts():
    matured_hedge_positions = HedgePosition.objects.filter(
        funding_tx_hash__isnull=False,
        maturity_timestamp__lte=timezone.now(),
        settlement__isnull=True
    )

    contract_addresses = []
    for hedge_position in matured_hedge_positions:
        update_contract_settlement.delay(hedge_position.address)
        contract_addresses.append(hedge_position.address)

    return contract_addresses


@shared_task(queue=_QUEUE_SETTLEMENT_UPDATE, time_limit=_TASK_TIME_LIMIT)
def update_contract_settlement(contract_address):
    hedge_position_obj = HedgePosition.objects.filter(address=contract_address).first()
    if not hedge_position_obj:
        return

    if not hedge_position_obj.settlement_service:
        return

    contract_data = get_contract_status(
        hedge_position_obj.address,
        hedge_position_obj.hedge_pubkey,
        hedge_position_obj.settlement_service.hedge_signature,
        settlement_service_scheme=hedge_position_obj.settlement_service.scheme,
        settlement_service_domain=hedge_position_obj.settlement_service.domain,
        settlement_service_port=hedge_position_obj.settlement_service.port,
    )

    if "settlement" in contract_data and isinstance(contract_data["settlement"], list):
        for settlement_data in contract_data["settlement"]:
            parse_oracle_message_response = parse_oracle_message(
                settlement_data["settlementMessage"],
                pubkey=settlement_data["oraclePublicKey"],
                signature=settlement_data["settlementSignature"],
            )
            hedge_settlement = HedgeSettlement.objects.filter(hedge_position=hedge_position_obj).first()
            if not hedge_settlement:
                hedge_settlement = HedgeSettlement()
                hedge_settlement.hedge_position = hedge_position_obj

            hedge_settlement.spending_transaction = settlement_data["spendingTransaction"]
            hedge_settlement.settlement_type = settlement_data["settlementType"]
            hedge_settlement.hedge_satoshis = settlement_data["hedgeSatoshis"]
            hedge_settlement.long_satoshis = settlement_data["longSatoshis"]

            hedge_settlement.oracle_pubkey = settlement_data["oraclePublicKey"]
            hedge_settlement.settlement_message = settlement_data["settlementMessage"]
            hedge_settlement.settlement_signature = settlement_data["settlementSignature"]

            if parse_oracle_message_response["success"]:
                price_data = parse_oracle_message_response["priceData"]
                hedge_settlement.settlement_price = price_data["priceValue"]
                hedge_settlement.settlement_price_sequence = price_data["priceSequence"]
                hedge_settlement.settlement_message_sequence = price_data["messageSequence"]
                hedge_settlement.settlement_message_timestamp = datetime.fromtimestamp(price_data["messageTimestamp"]).replace(tzinfo=pytz.UTC)

            hedge_settlement.save()

    send_settlement_update(hedge_position_obj)
    return contract_data
