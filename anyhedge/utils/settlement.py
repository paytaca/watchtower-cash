import json
import base64
import requests
from django.db import models
from cashaddress import convert
from .contract import compile_contract_from_hedge_position
from .price_oracle import (
    save_price_oracle_message,
    get_price_messages,
)
from ..js.runner import AnyhedgeFunctions
from ..models import (
    HedgePosition,
    Oracle,
    PriceOracleMessage,
)

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
        settlement__isnull=True, # not settled
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
    cash_address = convert.to_cash_address(contract_address)
    address = cash_address.replace("bitcoincash:", "")
    query = {
        "v": 3,
        "q": {
            "find": { "in.e.a": address },
            "limit": 10,
            "project": { "tx.h": 1 },
        }
    }

    # get used utxos of contract address
    query_string = json.dumps(query)
    query_bytes = query_string.encode('ascii')
    query_b64 = base64.b64encode(query_bytes)
    url = f"https://bitdb.bch.sx/q/{query_b64.decode()}"

    data = requests.get(url).json()
    tx_hashes = []

    txs = [*data["c"], *data["u"]]
    for tx in txs:
        tx_hashes.append(tx["tx"]["h"])

    if len(tx_hashes) == 0:
        return []

    # get raw transactions of used utxos
    response = requests.post(
        "https://rest1.biggestfan.net/v2/rawtransactions/getRawTransaction",
        data = json.dumps({ "txids": tx_hashes, "verbose": False }),
        headers = {'Content-type': 'application/json', 'Accept': 'text/plain'},
    )
    raw_transactions = response.json()
    if not isinstance(raw_transactions, list):
        return []

    # parse raw transactions to settlements
    parse_settlement_txs_response = AnyhedgeFunctions.parseSettlementTransactions(raw_transactions)

    settlements = []
    if not parse_settlement_txs_response["success"]:
        return settlements

    for settlement in parse_settlement_txs_response["settlements"]:
        if not settlement:
            continue
        
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
        "hedgeSatoshis": mutual_redemption_obj.hedge_satoshis,
        "longSatoshis": mutual_redemption_obj.long_satoshis,
        "hedgeSchnorrSig": mutual_redemption_obj.hedge_schnorr_sig,
        "longSchnorrSig": mutual_redemption_obj.long_schnorr_sig,
        "settlementPrice": mutual_redemption_obj.settlement_price,
    }

    return AnyhedgeFunctions.completeMutualRedemption(contract_data, mutual_redemption_data)
