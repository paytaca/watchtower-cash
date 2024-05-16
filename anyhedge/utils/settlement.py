import json
import base64
import requests
from django.db import models
from cashaddress import convert
from .api import TransactionMetaAttribute
from .contract import compile_contract_from_hedge_position
from .price_oracle import (
    save_price_oracle_message,
    get_price_messages,
)
from ..js.runner import AnyhedgeFunctions
from ..models import (
    HedgePosition,
    HedgeSettlement,
    HedgePositionFunding,
    Oracle,
    PriceOracleMessage,
)

from main.utils.queries.bchn import BCHN
from main.utils.address_scan import get_bch_transactions


def get_contracts_for_liquidation():
    liquidation_price_msg_subquery = PriceOracleMessage.objects.filter(
        models.Q(price_value__lte=models.OuterRef('_low_lq_price')) | models.Q(price_value__gte=models.OuterRef('_high_lq_price')),
        pubkey=models.OuterRef('oracle_pubkey'),
        message_timestamp__gte=models.OuterRef('start_timestamp'),
        message_timestamp__lte=models.OuterRef('maturity_timestamp'),
    ).order_by(
        'message_timestamp'
    ).values(
        'message_sequence',
    )

    unsettled_contracts = HedgePosition.objects.filter(
        funding_tx_hash__isnull=False, # funded
        settlements__isnull=True, # not settled
    )
    unsettled_contracts_for_liquidation = unsettled_contracts.annotate(
        _low_lq_price=unsettled_contracts.Annotations.low_liquidation_price,
        _high_lq_price=unsettled_contracts.Annotations.high_liquidation_price,
    ).annotate(
        liquidation_message_sequence=models.Subquery(liquidation_price_msg_subquery[:1])
    ).filter(
        liquidation_message_sequence__isnull=False
    )

    return unsettled_contracts_for_liquidation


def search_settlement_tx(contract_address):
    bchn = BCHN()
    cash_address = convert.to_cash_address(contract_address)

    history = get_bch_transactions(cash_address)
    txids = [tx["tx_hash"] for tx in history]

    raw_transactions = []
    funding_tx_map = {}
    for txid in txids:
        tx_data = bchn.get_transaction(txid, include_hex=True)
        for input_data in tx_data["inputs"]:
            if input_data["address"] == cash_address:
                raw_transactions.append(tx_data["hex"])
                funding_tx_map[txid] = input_data["txid"]

    if len(raw_transactions) == 0:
        return []

    # parse raw transactions to settlements
    parse_settlement_txs_response = AnyhedgeFunctions.parseSettlementTransactions(raw_transactions)

    settlements = []
    if not parse_settlement_txs_response["success"]:
        return settlements

    for settlement in parse_settlement_txs_response["settlements"]:
        if not settlement:
            continue

        settlement_data = settlement["settlement"]
        settlement_txid = settlement_data.get("settlementTransactionHash") or settlement_data.get("spendingTransaction")
        if settlement_txid and settlement_txid in funding_tx_map:
            settlement["funding_tx_hash"] = funding_tx_map[settlement_txid]

        if settlement["address"] == contract_address:
            settlements.append(settlement)

    return settlements


def settle_hedge_position_maturity(hedge_position_obj):
    contract_data = compile_contract_from_hedge_position(hedge_position_obj)

    oracle = Oracle.objects.filter(pubkey=hedge_position_obj.oracle_pubkey).first()
    oracle_info = None
    if oracle and oracle.relay and oracle.port:
        oracle_info = {
            "oracleRelay": oracle.relay,
            "oracleRelayPort": oracle.port,
        }

    return AnyhedgeFunctions.settleContractMaturity(contract_data, oracle_info)


def liquidate_hedge_position(hedge_position_obj, message_sequence):
    contract_data = compile_contract_from_hedge_position(hedge_position_obj)
    settlement_price_message = PriceOracleMessage.objects.filter(
        pubkey=hedge_position_obj.oracle_pubkey,
        message_sequence=message_sequence,
    ).first()
    previous_price_message = PriceOracleMessage.objects.filter(
        pubkey=hedge_position_obj.oracle_pubkey,
        message_sequence=message_sequence-1,
    ).first()

    if not settlement_price_message or not previous_price_message:
        oracle = Oracle.objects.filter(pubkey=hedge_position_obj.oracle_pubkey).first()
        price_messages = get_price_messages(
            hedge_position_obj.oracle_pubkey,
            relay= oracle.relay if oracle else None,
            port= oracle.port if oracle else None,
            max_message_sequence=message_sequence,
            count=2,
        )
        settlement_price_message = save_price_oracle_message(price_messages[0])
        previous_price_message = save_price_oracle_message(price_messages[1])

    prevPriceMessage = { "message": previous_price_message.message, "signature": previous_price_message.signature }
    settlementPriceMessage = { "message": settlement_price_message.message, "signature": settlement_price_message.signature }
    return AnyhedgeFunctions.liquidateContract(contract_data, prevPriceMessage, settlementPriceMessage)


def complete_mutual_redemption(mutual_redemption_obj):
    contract_data = compile_contract_from_hedge_position(mutual_redemption_obj.hedge_position)

    mutual_redemption_data = {
        "redemptionType": mutual_redemption_obj.redemption_type,
        "shortSatoshis": mutual_redemption_obj.short_satoshis,
        "longSatoshis": mutual_redemption_obj.long_satoshis,
        "shortSchnorrSig": mutual_redemption_obj.short_schnorr_sig,
        "longSchnorrSig": mutual_redemption_obj.long_schnorr_sig,
        "settlementPrice": mutual_redemption_obj.settlement_price,
    }

    return AnyhedgeFunctions.completeMutualRedemption(contract_data, mutual_redemption_data)


def save_settlement_data_from_mutual_redemption(hedge_position_obj):
    mutual_redemption_obj = None
    try:
        mutual_redemption_obj = hedge_position_obj.mutual_redemption
    except HedgePosition.mutual_redemption.RelatedObjectDoesNotExist:
        return

    if not mutual_redemption_obj or not mutual_redemption_obj.tx_hash:
        return

    settlement_obj = hedge_position_obj.settlements.filter(spending_transaction=mutual_redemption_obj.tx_hash).first()
    if not settlement_obj: 
        settlement_obj = HedgeSettlement(hedge_position=hedge_position_obj)

    settlement_obj.spending_transaction = mutual_redemption_obj.tx_hash
    settlement_obj.settlement_type = "mutual"
    settlement_obj.short_satoshis = mutual_redemption_obj.short_satoshis
    settlement_obj.long_satoshis = mutual_redemption_obj.long_satoshis
    settlement_obj.oracle_pubkey = hedge_position_obj.oracle_pubkey
    if mutual_redemption_obj.settlement_price:
        settlement_obj.settlement_price = mutual_redemption_obj.settlement_price
    settlement_obj.save()

    if mutual_redemption_obj.funding_tx_hash:
        HedgePositionFunding.objects.filter(
            hedge_position=hedge_position_obj,
            tx_hash=mutual_redemption_obj.funding_tx_hash,
        ).update(settlement=settlement_obj)

    try:
        attach_settlement_tx_to_wallet_history_meta(settlement_obj)
    except:
        pass

    return settlement_obj


def attach_settlement_tx_to_wallet_history_meta(settlement_obj):
    filter_kwargs = dict(
        txid=settlement_obj.spending_transaction,
        wallet_hash="",
        system_generated=True,
        key="anyhedge_settlement_tx",
    )
    defaults = dict(value=settlement_obj.hedge_position.address)
    settlement_tx_attr, _ = TransactionMetaAttribute.objects.update_or_create(defaults=defaults, **filter_kwargs)
    return settlement_tx_attr
