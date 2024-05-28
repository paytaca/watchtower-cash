import logging
import pytz
from datetime import datetime
from celery import shared_task
from django.db import models
from django.utils import timezone
from .models import (
    MutualRedemption,
    HedgePosition,
    HedgeSettlement,
    HedgePositionFunding,
    Oracle,
    PriceOracleMessage,
)
from .utils.api import broadcast_transaction
from .utils.auth_token import get_settlement_service_auth_token
from .utils.contract import get_contract_status
from .utils.funding import (
    complete_funding_proposal,
    search_funding_tx,
    get_tx_hash,
    validate_funding_transaction,
    attach_funding_tx_to_wallet_history_meta,
)
from .utils.liquidity import resolve_liquidity_fee
from .utils.price_oracle import (
    get_price_messages,
    parse_oracle_message,
    save_price_oracle_message,
)
from .utils.push_notification import (
    send_contract_matured,
)
from .utils.settlement import (
    get_contracts_for_liquidation,
    search_settlement_tx,
    settle_hedge_position_maturity,
    liquidate_hedge_position,
    complete_mutual_redemption,
    save_settlement_data_from_mutual_redemption,
    attach_settlement_tx_to_wallet_history_meta,
)
from .utils.websocket import (
    send_settlement_update,
    send_funding_tx_update,
)


## CELERY QUEUES
_TASK_TIME_LIMIT = 300 # 5 minutes
_QUEUE_PRICE_ORACLE = "anyhedge__price_oracle"
_QUEUE_SETTLEMENT_UPDATE = "anyhedge__settlement_updates"
_QUEUE_FUNDING_PARSER = "anyhedge__funding_parser"


LOGGER = logging.getLogger(__name__)


@shared_task(queue=_QUEUE_PRICE_ORACLE, time_limit=_TASK_TIME_LIMIT)
def check_new_price_messages():
    pubkeys = Oracle.objects.filter(active=True).values_list("pubkey", flat=True).distinct()
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
        count = min(count, 5) # setup a hard limit

    relay = None
    port = None
    oracle = Oracle.objects.filter(pubkey=oracle_pubkey).first()
    if oracle:
        relay = oracle.relay
        port = oracle.port

    price_messages = get_price_messages(
        oracle_pubkey,
        relay=relay, port=port,
        min_message_timestamp=latest_timestamp, count=count,
    )

    for price_message in price_messages:
        save_price_oracle_message(oracle_pubkey, price_message)

@shared_task(queue=_QUEUE_SETTLEMENT_UPDATE, time_limit=_TASK_TIME_LIMIT)
def update_contracts_for_liquidation():
    contracts_for_liquidation = get_contracts_for_liquidation()

    contract_addresses = []
    for contract in contracts_for_liquidation:
        liquidate_contract.delay(contract.address, contract.liquidation_message_sequence)
        contract_addresses.append(contract.address)
    return contract_addresses


@shared_task(queue=_QUEUE_SETTLEMENT_UPDATE, time_limit=_TASK_TIME_LIMIT)
def update_matured_contracts():
    matured_hedge_positions = HedgePosition.objects.filter(
        funding_tx_hash__isnull=False,
        maturity_timestamp__lte=timezone.now(),
        settlements__isnull=True
    ).exclude(
        funding_tx_hash=""
    )

    contract_addresses = []
    for hedge_position in matured_hedge_positions:
        try:
            if hedge_position.settlement_service:
                update_contract_settlement_from_service.delay(hedge_position.address)
        except HedgePosition.settlement_service.RelatedObjectDoesNotExist:
            settle_contract_maturity.delay(hedge_position.address)

        try:
            send_contract_matured(hedge_position)
        except Exception as exception:
            LOGGER.exception(exception)

        contract_addresses.append(hedge_position.address)

    return contract_addresses

def __save_settlement(settlement_data, hedge_position_obj, funding_txid=None):
    LOGGER.info(f"SAVING SETTLEMENT FOR '{hedge_position_obj.address}': {funding_txid} - {settlement_data}")

    # NOTE: handling both new & old implementation since external settlement service might be
    #       using old one. remove old implementation after upgrade is stable
    if "settlementTransactionHash" in settlement_data:
        settlement_txid = settlement_data["settlementTransactionHash"]
        short_satoshis = settlement_data["shortPayoutInSatoshis"]
        long_satoshis = settlement_data["longPayoutInSatoshis"]
    else:
        settlement_txid = settlement_data["spendingTransaction"]
        short_satoshis = settlement_data["shortSatoshis"]
        long_satoshis = settlement_data["longSatoshis"]

    hedge_settlement = HedgeSettlement.objects.filter(
        hedge_position=hedge_position_obj,
        spending_transaction=settlement_txid,
    ).first()
    if not hedge_settlement:
        hedge_settlement = HedgeSettlement()
        hedge_settlement.hedge_position = hedge_position_obj
        hedge_settlement.spending_transaction = settlement_txid

    hedge_settlement.settlement_type = settlement_data["settlementType"]
    hedge_settlement.short_satoshis = short_satoshis
    hedge_settlement.long_satoshis = long_satoshis

    if "settlementMessage" in settlement_data:
        settlement_message = settlement_data["settlementMessage"]
        oracle_pubkey = settlement_data.get("oraclePublicKey", None) or hedge_position_obj.oracle_pubkey
        settlement_signature = settlement_data.get("settlementSignature", None)
        parse_oracle_message_response = parse_oracle_message(
            settlement_message,
            pubkey=oracle_pubkey,
            signature=settlement_signature,
        )

        hedge_settlement.oracle_pubkey = oracle_pubkey
        hedge_settlement.settlement_message = settlement_message
        hedge_settlement.settlement_signature = settlement_signature

        if parse_oracle_message_response["success"]:
            price_data = parse_oracle_message_response["priceData"]
            hedge_settlement.settlement_price = price_data["priceValue"]
            hedge_settlement.settlement_price_sequence = price_data["priceSequence"]
            hedge_settlement.settlement_message_sequence = price_data["messageSequence"]
            hedge_settlement.settlement_message_timestamp = datetime.fromtimestamp(price_data["messageTimestamp"]).replace(tzinfo=pytz.UTC)

    hedge_settlement.save()
    if funding_txid:
        fundings_queryset = HedgePositionFunding.objects.filter(
            hedge_position=hedge_position_obj,
            tx_hash=funding_txid,
        )
        if not fundings_queryset.count():
            LOGGER.exception(f"Unable to find funding record '{funding_txid}' for settlement")
        fundings_queryset.update(settlement=hedge_settlement)

    try:
        attach_settlement_tx_to_wallet_history_meta(hedge_settlement)
    except Exception as exception:
        LOGGER.error(f"SETTLEMENT TX META ERROR: {hedge_settlement.hedge_position.address}")
        LOGGER.exception(exception)
    return hedge_settlement


@shared_task(queue=_QUEUE_SETTLEMENT_UPDATE, time_limit=_TASK_TIME_LIMIT)
def update_contract_settlement(contract_address, new_task=True):
    response = { "success": False }
    hedge_position_obj = HedgePosition.objects.filter(address=contract_address).first()
    if not hedge_position_obj:
        response["success"] = False
        response["error"] = "Contract not found"
        return response

    try:
        if hedge_position_obj.settlement_service:
            if new_task:
                return update_contract_settlement_from_service.delay(hedge_position_obj.address)
            else:
                return update_contract_settlement_from_service(hedge_position_obj.address)
    except HedgePosition.settlement_service.RelatedObjectDoesNotExist:
        if new_task:
            return update_contract_settlement_from_chain.delay(hedge_position_obj.address)
        else:
            return update_contract_settlement_from_chain(hedge_position_obj.address)

    return response


@shared_task(queue=_QUEUE_SETTLEMENT_UPDATE, time_limit=_TASK_TIME_LIMIT)
def update_contract_settlement_from_service(contract_address):
    response = { "success": False }
    hedge_position_obj = HedgePosition.objects.filter(address=contract_address).first()
    if not hedge_position_obj:
        response["success"] = False
        response["error"] = "Contract not found"
        return response

    if not hedge_position_obj.settlement_service:
        response["success"] = False
        response["error"] = "Settlement service not found"
        return response

    access_pubkey = ""
    access_signature = ""
    if hedge_position_obj.settlement_service.short_signature:
        access_pubkey = hedge_position_obj.short_pubkey
        access_signature = hedge_position_obj.settlement_service.short_signature
    elif hedge_position_obj.settlement_service.long_signature:
        access_pubkey = hedge_position_obj.long_pubkey
        access_signature = hedge_position_obj.settlement_service.long_signature

    try:
        contract_data = get_contract_status(
            hedge_position_obj.address,
            access_pubkey,
            access_signature,
            settlement_service_scheme=hedge_position_obj.settlement_service.scheme,
            settlement_service_domain=hedge_position_obj.settlement_service.domain,
            settlement_service_port=hedge_position_obj.settlement_service.port,
            authentication_token=hedge_position_obj.settlement_service.auth_token,
        )
    except Exception as exception:
        if str(exception).strip() != "Request failed with status code 401":
            raise exception
        settlement_service = hedge_position_obj.settlement_service
        settlement_service.auth_token = get_settlement_service_auth_token(settlement_service.scheme, settlement_service.domain, settlement_service.port)
        contract_data = get_contract_status(
            hedge_position_obj.address,
            access_pubkey,
            access_signature,
            settlement_service_scheme=settlement_service.scheme,
            settlement_service_domain=settlement_service.domain,
            settlement_service_port=settlement_service.port,
            authentication_token=settlement_service.auth_token,
        )
        settlement_service.save()

    settlements = []
    # NOTE: handling both new & old implementation since external settlement service might be
    #       using old one. remove old implementation after upgrade is stable
    if "settlement" in contract_data and isinstance(contract_data["settlement"], list):
        for settlement_data in contract_data["settlement"]:
            __save_settlement(settlement_data, hedge_position_obj)
        settlements = contract_data["settlement"]
    elif "fundings" in contract_data and isinstance(contract_data["fundings"], list):
        for funding_data in contract_data["fundings"]:
            if not funding_data.get("settlement"):
                continue

            settlements.append(funding_data["settlement"])
            __save_settlement(
                funding_data["settlement"],
                hedge_position_obj,
                funding_txid=funding_data["fundingTransactionHash"]
            )

    send_settlement_update(hedge_position_obj)

    response["success"] = True
    response["settlements"] = settlements
    return response


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
        funding_tx_hash = settlement.get("funding_tx_hash")
        hedge_settlement = __save_settlement(settlement_data, hedge_position_obj, funding_txid=funding_tx_hash)
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

    settlement_search_response = update_contract_settlement(contract_address, new_task=False)
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
    try:
        funding_tx_hash = settle_hedge_position_maturity_response["funding"]["fundingTransactionHash"]
    except (TypeError, KeyError):
        funding_tx_hash = None

    if not settle_hedge_position_maturity_response["success"] or not settlement_data:
        response["success"] = False
        if "error" in settle_hedge_position_maturity_response:
            response["error"] = settle_hedge_position_maturity_response["error"]
        else:
            response["error"] = "encountered error in settling contract maturity"

        return response
    
    hedge_settlement = __save_settlement(
        settlement_data,
        hedge_position_obj,
        funding_txid=funding_tx_hash,
    )

    send_settlement_update(hedge_position_obj)

    response["success"] = True
    response["settlements"] = [settlement_data]
    return response
 

@shared_task(queue=_QUEUE_SETTLEMENT_UPDATE, time_limit=_TASK_TIME_LIMIT)
def liquidate_contract(contract_address, message_sequence):
    LOGGER.info(f"Liquidating contract({contract_address})")
    response = { "success": False }
    hedge_position_obj = HedgePosition.objects.filter(address=contract_address).first()
    if not hedge_position_obj:
        response["success"] = False
        response["error"] = "contract not found"
        return response

    if hedge_position_obj.settlements.count():
        response["success"] = True
        response["message"] = "contract settlement already exists"
        return response

    # attempt to check if contract is settled but not yet saved in db
    settlement_search_response = update_contract_settlement(contract_address, new_task=False)
    if settlement_search_response["success"] and \
        isinstance(settlement_search_response.get("settlements", None), list) and \
        len(settlement_search_response["settlements"]):

        response["success"] = True
        response["message"] = "contract already settled"
        response["settlements"] = settlement_search_response["settlements"]
        return response


    if not hedge_position_obj.get_hedge_position_funding():
        contract_funding_validation = validate_contract_funding(hedge_position_obj.address)
        if not contract_funding_validation["success"]:
            response["success"] = False
            response["error"] = "contract funding not validated"
            return response


    liquidation_response = liquidate_hedge_position(hedge_position_obj, message_sequence)
    settlement_data = liquidation_response.get("settlementData", None)
    try:
        funding_tx_hash = liquidation_response["funding"]["fundingTransactionHash"]
    except (TypeError, KeyError):
        funding_tx_hash = None

    if not liquidation_response["success"] or not settlement_data:
        response["success"] = False
        if "error" in liquidation_response:
            response["error"] = liquidation_response["error"]
        else:
            response["error"] = "encountered error in liquidating contract"

        return response
    
    hedge_settlement = __save_settlement(
        settlement_data,
        hedge_position_obj,
        funding_txid=funding_tx_hash,
    )

    send_settlement_update(hedge_position_obj)

    response["success"] = True
    response["message"] = f"contract({hedge_position_obj.address}) liquidated at message sequence {message_sequence}"
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
        broadcast_response = broadcast_transaction(tx_hex)

        if broadcast_response["success"]:
            tx_hash = broadcast_response["txid"]
            hedge_position_obj.funding_tx_hash = tx_hash
            hedge_position_obj.save()
            response["success"] = True
            response["tx_hash"] = tx_hash
            response["message"] = "submitted funding transaction"

            try:
                metadata_obj = hedge_position_obj.metadata
                metadata_obj.total_hedge_funding_sats = hedge_position_obj.hedge_funding_proposal.tx_value
                metadata_obj.total_long_funding_sats = hedge_position_obj.long_funding_proposal.tx_value
                if not metadata_obj.network_fee:
                    total_funding_sats = metadata_obj.total_hedge_funding_sats + metadata_obj.total_long_funding_sats
                    total_input_sats = hedge_position_obj.total_sats_with_fee
                    metadata_obj.network_fee = total_funding_sats - total_input_sats
                metadata_obj.save()
            except HedgePosition.metadata.RelatedObjectDoesNotExist:
                LOGGER.info(f"skipping metadata update for contract({hedge_position_obj.address}), no metadata obj found")
            except Exception as error:
                LOGGER.exception(error)

            send_funding_tx_update(hedge_position_obj, tx_hash=tx_hash)
            return response
        else:
            response["success"] = False
            response["error"] = broadcast_response["error"]
            return response

    except Exception as exception:
        LOGGER.exception(exception)
        response["success"] = False
        response["error"] = str(exception)
        return response


@shared_task(queue=_QUEUE_FUNDING_PARSER, time_limit=_TASK_TIME_LIMIT)
def validate_contract_funding(contract_address, save=True):
    LOGGER.info(f"Attempting to validate funding for contract({contract_address})")
    response = { "success": False, "error": None }

    hedge_position_obj = HedgePosition.objects.filter(address=contract_address).first()
    if not hedge_position_obj.funding_tx_hash:
        response["success"] = False
        response["error"] = "funding transaction not found"
        return response

    funding_tx_validation = validate_funding_transaction(hedge_position_obj.funding_tx_hash, hedge_position_obj.address)
    if not funding_tx_validation["valid"]:
        response["success"] = False
        response["error"] = "invalid funding transaction"
        return response

    if save:
        defaults = {
            "funding_output": funding_tx_validation["funding_output"],
            "funding_satoshis": funding_tx_validation["funding_satoshis"],
            "validated": True,
        }

        HedgePositionFunding.objects.update_or_create(
            hedge_position=hedge_position_obj,
            tx_hash=hedge_position_obj.funding_tx_hash,
            defaults=defaults
        )
        hedge_position_obj.funding_tx_hash_validated = True
        hedge_position_obj.save()
        try:
            attach_funding_tx_to_wallet_history_meta(hedge_position_obj)
        except Exception as exception:
            LOGGER.error(f"FUNDING TX META ERROR: {hedge_position_obj.address}")
            LOGGER.exception(exception)

    response["success"] = True
    response["validation"] = funding_tx_validation
    return response

@shared_task(queue=_QUEUE_SETTLEMENT_UPDATE, time_limit=_TASK_TIME_LIMIT)
def redeem_contract(contract_address):
    response = { "success": False }
    mutual_redemption_obj = MutualRedemption.objects.filter(hedge_position__address=contract_address).first()
    if not mutual_redemption_obj:
        response["success"] = False
        response["error"] = "Mutual redemption not found"
        return response

    if mutual_redemption_obj.hedge_position.settlements.count():
        response["success"] = False
        response["error"] = "Contract is already settled"
    else:
        settlement_search_response = update_contract_settlement(contract_address, new_task=False)
        if settlement_search_response["success"] and \
            isinstance(settlement_search_response.get("settlements", None), list) and \
            len(settlement_search_response["settlements"]):

            response["success"] = False
            response["error"] = "Contarct is already settled"
            response["settlements"] = settlement_search_response["settlements"]
            return response

    if mutual_redemption_obj.tx_hash:
        response["success"] = False
        response["error"] = "Mutual redemption is already completed"
        return response

    if not mutual_redemption_obj.short_schnorr_sig or not mutual_redemption_obj.long_schnorr_sig:
        response["success"] = False
        response["error"] = "Incomplete signatures"
        return response

    mutual_redemption_response = complete_mutual_redemption(mutual_redemption_obj)
    if not mutual_redemption_response["success"]:
        response["success"] = False
        response["error"] = mutual_redemption_response.get("error", None) or "Error in completing redemption"
        return response

    mutual_redemption_obj.tx_hash = mutual_redemption_response["settlementTxid"]
    mutual_redemption_obj.funding_tx_hash = mutual_redemption_response["fundingTxid"]
    mutual_redemption_obj.save()
    try:
        settlement_obj = save_settlement_data_from_mutual_redemption(mutual_redemption_obj.hedge_position)
        if settlement_obj:
            send_settlement_update(mutual_redemption_obj.hedge_position)
    except Exception as error:
        LOGGER.exception(error)
    response["success"] = True
    response["tx_hash"] = mutual_redemption_response
    return response


@shared_task(queue=_QUEUE_FUNDING_PARSER, time_limit=_TASK_TIME_LIMIT)
def parse_contract_liquidity_fee(contract_address, hard_update=False):
    response = { "success": False, "error": None }
    hedge_position_obj = HedgePosition.objects.get(address=contract_address)
    if not hedge_position_obj.funding_tx_hash:
        response["success"] = False
        response["error"] = "No funding transaction"
        return response

    metadata_obj = resolve_liquidity_fee(hedge_position_obj, hard_update=hard_update)
    if metadata_obj:
        response["success"] = True
    return response

@shared_task(queue=_QUEUE_FUNDING_PARSER, time_limit=_TASK_TIME_LIMIT)
def parse_contracts_liquidity_fee():
    NO_CONTRACTS_TO_PARSE = 5 
    hedge_position_objects = HedgePosition.objects.annotate(
        funding_tx_len=models.functions.Coalesce(
            models.functions.Length("funding_tx_hash"), models.Value(0)
        ),
        short_wallet_hash_len=models.functions.Length("short_wallet_hash"),
        long_wallet_hash_len=models.functions.Length("long_wallet_hash"),
    ).filter(
        models.Q(short_wallet_hash_len__gt=0, long_wallet_hash_len=0) | models.Q(short_wallet_hash_len=0, long_wallet_hash_len__gt=0),
        funding_tx_len__gt=0,
        metadata__isnull=True,
    )[:NO_CONTRACTS_TO_PARSE]

    contracts_parsed = []
    for hedge_position_obj in hedge_position_objects:
        try:
            resolve_liquidity_fee(hedge_position_obj)
            contracts_parsed.append(hedge_position_obj.address)
        except Exception:
            pass

    return contracts_parsed
