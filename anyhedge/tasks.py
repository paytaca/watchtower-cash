import logging
import pytz
from datetime import datetime
from celery import shared_task
from django.db import models
from django.utils import timezone
from main.tasks import broadcast_transaction
from .models import (
    HedgePosition,
    HedgeSettlement,
    HedgePositionFunding,
    Oracle,
    PriceOracleMessage,
)
from .utils.contract import get_contract_status
from .utils.funding import (
    complete_funding_proposal,
    search_funding_tx,
    get_tx_hash,
    validate_funding_transaction,
)
from .utils.price_oracle import (
    get_price_messages,
    parse_oracle_message,
    save_price_oracle_message,
)
from .utils.settlement import (
    search_settlement_tx,
    settle_hedge_position_maturity,
)
from .utils.websocket import (
    send_settlement_update,
    send_funding_tx_update,
)


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
        save_price_oracle_message(oracle_pubkey, price_message)


@shared_task(queue=_QUEUE_SETTLEMENT_UPDATE, time_limit=_TASK_TIME_LIMIT)
def update_matured_contracts():
    matured_hedge_positions = HedgePosition.objects.filter(
        funding_tx_hash__isnull=False,
        maturity_timestamp__lte=timezone.now(),
        settlement__isnull=True
    )

    contract_addresses = []
    for hedge_position in matured_hedge_positions:
        try:
            if hedge_position.settlement_service:
                update_contract_settlement.delay(hedge_position.address)
        except HedgePosition.settlement_service.RelatedObjectDoesNotExist:
            settle_contract_maturity.delay(hedge_position.address)

        contract_addresses.append(hedge_position.address)

    return contract_addresses

def __save_settlement(settlement_data, hedge_position_obj):
    hedge_settlement = HedgeSettlement.objects.filter(hedge_position=hedge_position_obj).first()
    if not hedge_settlement:
        hedge_settlement = HedgeSettlement()
        hedge_settlement.hedge_position = hedge_position_obj

    parse_oracle_message_response = parse_oracle_message(
        settlement_data["settlementMessage"],
        pubkey=settlement_data["oraclePublicKey"],
        signature=settlement_data["settlementSignature"],
    )

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
    return hedge_settlement

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
            __save_settlement(settlement_data, hedge_position_obj)

    send_settlement_update(hedge_position_obj)
    return contract_data


@shared_task(queue=_QUEUE_SETTLEMENT_UPDATE, time_limit=_TASK_TIME_LIMIT)
def update_contract_settlement_from_chain(contract_address):
    LOGGER.info(f"Searching for settlement transaction of contract({contract_address})")
    response = { "success": False }

    hedge_position_obj = HedgePosition.objects.filter(address=contract_address).first()
    if not hedge_position_obj:
        response["success"] = False
        response["error"] = "contract not found"
        return response

    settlements = search_settlement_tx(contract_address)
    if not isinstance(settlements, list) or len(settlements) == 0:
        response["success"] = False
        response["error"] = "no settlements found"

    found_settlement = False
    for settlement in settlements:
        settlement_data = settlement["settlement"]
        hedge_settlement = __save_settlement(settlement_data, hedge_position_obj)
        found_settlement = True

    if found_settlement:
        send_settlement_update(hedge_position_obj)

    response["success"] = True
    response["settlements"] = settlements
    return response


@shared_task(queue=_QUEUE_SETTLEMENT_UPDATE, time_limit=_TASK_TIME_LIMIT)
def settle_contract_maturity(contract_address):
    LOGGER.info(f"Attempting to settle maturity of contract({contract_address})")
    response = { "success": False }

    settlement_search_response = update_contract_settlement_from_chain(contract_address)
    if settlement_search_response["success"] and \
        isinstance(settlement_search_response.get("settlements", None), list) and \
        len(settlement_search_response["settlements"]):

        response["success"] = True
        response["settlements"] = settlement_search_response["settlements"]
        return response

    hedge_position_obj = HedgePosition.objects.filter(address=contract_address).first()
    if not hedge_position_obj:
        response["success"] = False
        response["error"] = "contract not found"

    if not hedge_position_obj.get_hedge_position_funding():
        contract_funding_validation = validate_contract_funding(hedge_position_obj.address)
        if not contract_funding_validation["success"]:
            response["success"] = False
            response["error"] = "contract funding not validated"
            return response

    settle_hedge_position_maturity_response = settle_hedge_position_maturity(hedge_position_obj)
    settlement_data = settle_hedge_position_maturity_response.get("settlementData", None)
    if not settle_hedge_position_maturity_response["success"] or not settlement_data:
        response["success"] = False
        if "error" in settle_hedge_position_maturity_response:
            response["error"] = settle_hedge_position_maturity_response["error"]
        else:
            response["error"] = "encountered error in settling contract maturity"

        return response
    
    hedge_settlement = __save_settlement(settlement_data, hedge_position_obj)

    send_settlement_update(hedge_position_obj)

    response["success"] = True
    response["settlements"] = [settlement_data]
    return response
 

@shared_task(queue=_QUEUE_SETTLEMENT_UPDATE, time_limit=_TASK_TIME_LIMIT)
def complete_contract_funding(contract_address):
    LOGGER.info(f"Attempting to complete funding for contract({contract_address})")
    response = { "success": False, "tx_hash": "", "error": "", "message": "" }

    hedge_position_obj = HedgePosition.objects.filter(address=contract_address).first()
    if not hedge_position_obj:
        response["success"] = False
        response["error"] = "contract not found"

    if hedge_position_obj.funding_tx_hash:
        response["success"] = True
        response["tx_hash"] = hedge_position_obj.funding_tx_hash
        response["message"] = "funding transaction already in db"
        return response

    funding_tx_hash = search_funding_tx(hedge_position_obj.address)
    if funding_tx_hash:
        hedge_position_obj.funding_tx_hash = funding_tx_hash
        hedge_position_obj.save()
        response["success"] = True
        response["tx_hash"] = funding_tx_hash
        response["message"] = "found funding transaction in chain"
        return response

    try:
        complete_funding_proposal_response = complete_funding_proposal(hedge_position_obj)
        if not complete_funding_proposal_response["success"]:
            response["success"] = False
            response["error"] = complete_funding_proposal_response["error"]
            return response

        tx_hex = complete_funding_proposal_response["fundingTxHex"]
        success, result = broadcast_transaction(tx_hex)
        if 'already have transaction' in result:
            success = True

        if success:
            tx_hash = result.split(' ')[-1]
            hedge_position_obj.funding_tx_hash = tx_hash
            hedge_position_obj.save()
            response["success"] = True
            response["tx_hash"] = tx_hash
            response["message"] = "submitted funding transaction"

            send_funding_tx_update(hedge_position_obj, tx_hash=tx_hash)
            return response
        else:
            response["success"] = False
            response["error"] = result
            return response

    except Exception as exception:
        response["success"] = False
        response["error"] = str(exception)
        return response


@shared_task(queue=_QUEUE_SETTLEMENT_UPDATE, time_limit=_TASK_TIME_LIMIT)
def validate_contract_funding(contract_address, save=True):
    LOGGER.info(f"Attempting to validate funding for contract({contract_address})")
    response = { "success": False, "error": None }

    hedge_position_obj = HedgePosition.objects.filter(address=contract_address).first()
    if not hedge_position_obj.funding_tx_hash:
        response["success"] = False
        response["error"] = "funding transaction not found"
        return response

    fee_address = None
    try:
        if hedge_position_obj.fee and hedge_position_obj.fee.address:
            fee_address = hedge_position_obj.fee.address
    except HedgePosition.fee.RelatedObjectDoesNotExist:
        pass

    funding_tx_validation = validate_funding_transaction(hedge_position_obj.funding_tx_hash, hedge_position_obj.address, fee_address=fee_address)
    if not funding_tx_validation["valid"]:
        response["success"] = False
        response["error"] = "invalid funding transaction"

    if save:
        defaults = {
            "funding_output": funding_tx_validation["funding_output"],
            "funding_satoshis": funding_tx_validation["funding_satoshis"],
        }
        if funding_tx_validation["fee_output"] >= 0 and funding_tx_validation["fee_satoshis"]:
            defaults["fee_output"] = funding_tx_validation["fee_output"]
            defaults["fee_satoshis"] = funding_tx_validation["fee_satoshis"]

        HedgePositionFunding.objects.update_or_create(tx_hash=hedge_position_obj.funding_tx_hash, defaults=defaults)
        hedge_position_obj.funding_tx_hash_validated = True
        hedge_position_obj.save()

    response["success"] = True
    response["validation"] = funding_tx_validation
    return response
