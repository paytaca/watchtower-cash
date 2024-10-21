import time
import json
import decimal
from django.conf import settings

from stablehedge import models
from stablehedge.utils.address import to_cash_address
from stablehedge.utils.transaction import tx_model_to_cashscript
from stablehedge.js.runner import ScriptFunctions

from .treasury_contract import (
    get_spendable_sats,
    get_bch_utxos,
)

from anyhedge import models as anyhedge_models
from anyhedge.utils.liquidity_provider import GeneralProtocolsLP
from anyhedge.utils.funding import calculate_funding_amounts
from anyhedge.utils.contract import (
    AnyhedgeException,
    create_contract,
    contract_data_to_obj,
    get_contract_status,
)


GP_LP = GeneralProtocolsLP()
REDIS_STORAGE = settings.REDISKV


def get_or_create_short_proposal(treasury_contract_address:str):
    existing_data = get_short_contract_proposal(treasury_contract_address)
    if existing_data:
        return existing_data

    return create_short_proposal(treasury_contract_address)


def create_short_proposal(treasury_contract_address:str):
    contract_data, settlement_service, funding_amounts, partial_tx, *_ = short_funds(treasury_contract_address)
    save_short_proposal_data(
        treasury_contract_address,
        contract_data,
        settlement_service,
        funding_amounts,
        partial_tx,
    )
    return contract_data, settlement_service, funding_amounts, partial_tx

def save_short_proposal_data(
    treasury_contract_address,
    contract_data,
    settlement_service,
    funding_amounts,
    partial_tx,
):
    timeout = funding_amounts["recalculate_after"]
    ttl = int(timeout - time.time()) - 5 # 5 seconds for margin

    result = [contract_data, settlement_service, funding_amounts, partial_tx]
    REDIS_KEY = f"treasury-contract-short-{treasury_contract_address}"

    REDIS_STORAGE.set(REDIS_KEY, GP_LP.json_parser.dumps(result), ex=ttl)
    return ttl

def get_short_contract_proposal(treasury_contract_address:str, recompile=True):
    treasury_contract = models.TreasuryContract.objects.get(address=treasury_contract_address)

    REDIS_KEY = f"treasury-contract-short-{treasury_contract.address}"
    try:
        data = REDIS_STORAGE.get(REDIS_KEY)
        contract_data, settlement_service, funding_amounts, partial_tx, *_ = GP_LP.json_parser.loads(data)

        if recompile:
            # there is a recompile check inside that will throw error if address mismatch
            contract_data_to_obj(contract_data)

        return contract_data, settlement_service, funding_amounts, partial_tx
    except (TypeError, json.JSONDecodeError):
        return
    except AnyhedgeException as exception:
        if exception.code == AnyhedgeException.ADDRESS_MISMATCH:
            return
        else:
            raise exception

def update_short_proposal_access_keys(treasury_contract_address:str, pubkey:str="", signature:str=""):
    result = get_short_contract_proposal(treasury_contract_address, recompile=True)
    contract_data, settlement_service, funding_amounts, partial_tx, *_ = result

    parameters = contract_data["parameters"]
    short_pubkey = parameters["shortMutualRedeemPublicKey"]
    long_pubkey = parameters["longMutualRedeemPublicKey"]
    if pubkey not in [short_pubkey, long_pubkey]:
        raise AnyhedgeException("Pubkey does not match any side", code="invalid_pubkey")

    contract_data2 = get_contract_status(
        contract_data["address"],
        pubkey,
        signature,
        settlement_service_scheme=settlement_service["scheme"],
        settlement_service_domain=settlement_service["host"],
        settlement_service_port=settlement_service["port"],
        authentication_token=settlement_service.get("auth_token", None),
    )
    print(f"contract_data2 |", GP_LP.json_parser.dumps(contract_data2, indent=2))
    if contract_data2["address"] != contract_data["address"]:
        raise AnyhedgeException("Address mismatch", code=AnyhedgeException.ADDRESS_MISMATCH)
    else:
        contract_data = contract_data2

    if pubkey == short_pubkey:
        settlement_service["short_signature"] = signature
    else:
        settlement_service["long_signature"] = signature

    save_short_proposal_data(
        treasury_contract_address,
        contract_data,
        settlement_service,
        funding_amounts,
        partial_tx,
    )

    return contract_data, settlement_service, funding_amounts, partial_tx


def short_funds(treasury_contract_address:str, pubkey1_wif=""):
    balance_data = get_spendable_sats(treasury_contract_address)
    spendable_sats = balance_data["spendable"]

    HEDGE_FUNDING_NETWORK_FEES = 2500 # sats
    SETTLEMENT_SERVICE_FEE = 3000 # sats
    # most preimum so far was around 1% for hedge, while 2.5% for short 
    # we set 5% for a large margin
    MAX_PREMIUM_PCTG = 0.05

    shortable_sats = (spendable_sats - HEDGE_FUNDING_NETWORK_FEES - SETTLEMENT_SERVICE_FEE) * (1-MAX_PREMIUM_PCTG)

    create_result = create_short_contract(
        treasury_contract_address,
        satoshis=shortable_sats,
        low_liquidation_multiplier = 0.5,
        high_liquidation_multiplier = 5.0,
        duration_seconds = 86400 # seconds = 1 day
    )

    if "contract_data" not in create_result:
        return create_result

    contract_data = create_result["contract_data"]
    settlement_service = create_result["settlement_service"]

    contract_proposal_data = GP_LP.contract_data_to_proposal(contract_data)

    # there is a recompile check inside that will throw error if address mismatch
    contract_data_to_obj(contract_data)

    funding_amounts = calculate_funding_amounts(
        contract_data,
        position=contract_data["metadata"]["takerSide"],
    )

    contract_proposal_data = GP_LP.contract_data_to_proposal(contract_data)

    service_fee_estimate = GP_LP.estimate_service_fee(
        contract_proposal_data,
        settlement_service=settlement_service,
    )
    proposal_data = GP_LP.propose_contract(contract_proposal_data)

    lp_fee = proposal_data["liquidityProviderFeeInSatoshis"]
    lp_timeout = proposal_data["renegotiateAfterTimestamp"]

    P2PKH_OUTPUT_FEE = decimal.Decimal(34)
    sats_to_fund = decimal.Decimal(funding_amounts["short"])
    sats_to_fund += P2PKH_OUTPUT_FEE + service_fee_estimate
    sats_to_fund += P2PKH_OUTPUT_FEE + lp_fee

    funding_amounts["liquidity_fee"] = int(lp_fee)
    funding_amounts["recalculate_after"] = int(lp_timeout)
    funding_amounts["settlement_service_fee"] = int(service_fee_estimate)
    funding_amounts["satoshis_to_fund"] = int(sats_to_fund)

    partial_tx = create_tx_for_funding_utxo(treasury_contract_address, int(sats_to_fund))
    return contract_data, settlement_service, funding_amounts, partial_tx

def create_short_contract(
    treasury_contract_address:str,
    price_obj:anyhedge_models.PriceOracleMessage=None,
    satoshis:int=0,
    low_liquidation_multiplier:float=0.5,
    high_liquidation_multiplier:float=5.0,
    duration_seconds:int=60 * 60 * 2, # 2 hours
):
    treasury_contract = models.TreasuryContract.objects.filter(address=treasury_contract_address).first()

    oracle_public_key = get_treasury_contract_oracle_pubkey(treasury_contract.address)
    if not oracle_public_key:
        return dict(success=False, error="No oracle pubkey found")

    price_obj = get_and_validate_price_message(oracle_public_key, price_obj=price_obj)
    if not isinstance(price_obj, anyhedge_models.PriceOracleMessage):
        return dict(success=False, error=price_obj)

    liquidity_info = GP_LP.liquidity_service_info()
    settlement_service = liquidity_info["settlementService"]

    constraints = liquidity_info["liquidityParameters"][oracle_public_key]
    intent = GP_LP.fit_intent_to_constraints(
        satoshis=satoshis,
        low_liquidation_multiplier = low_liquidation_multiplier,
        high_liquidation_multiplier = high_liquidation_multiplier,
        duration_seconds = duration_seconds, # 1 day
        constraints=constraints,
        start_price=price_obj.price_value,
        is_simple_hedge=False,
    )

    satoshis = intent[0]
    low_liquidation_multiplier = intent[1]
    high_liquidation_multiplier = intent[2]
    duration_seconds = intent[3]

    counter_party_data = GP_LP.prepare_contract_position(oracle_public_key, "long")
    if "errors" in counter_party_data:
        return dict(success=False, error=counter_party_data["errors"])

    # pubkey is used for signing mutual redemption
    # address is receiving address for payout
    # they can be from different wallets/wif
    # 
    # we use pubkey1 from the treasury contract's params since a pubkey must be provided
    short_pubkey = treasury_contract.pubkey1
    short_address = to_cash_address(treasury_contract.address, testnet = None)

    hedge_sats = int(satoshis / (1- 1/high_liquidation_multiplier))

    create_result = create_contract(
        satoshis=hedge_sats,
        low_price_multiplier=low_liquidation_multiplier,
        high_price_multiplier=high_liquidation_multiplier,
        duration_seconds=duration_seconds,
        taker_side="short",
        is_simple_hedge=False,
        short_address=short_address,
        short_pubkey=short_pubkey,
        long_address=counter_party_data["liquidityProvidersPayoutAddress"],
        long_pubkey=counter_party_data["liquidityProvidersMutualRedemptionPublicKey"],
        oracle_pubkey=oracle_public_key,
        price_oracle_message_sequence=price_obj.message_sequence,
    )
    contract_data = create_result["contractData"]

    long_sats = int(contract_data["metadata"]["shortInputInSatoshis"])
    if counter_party_data["availableLiquidityInSatoshis"] < long_sats:
        return dict(success=False, error="Not enough liquidity")

    return dict(contract_data=contract_data, settlement_service=settlement_service)

def get_treasury_contract_oracle_pubkey(treasury_contract_address:str):
    return models.RedemptionContract.objects. \
        filter(treasury_contract__address=treasury_contract_address) \
        .values_list("price_oracle_pubkey", flat=True) \
        .first()


def get_and_validate_price_message(oracle_public_key:str, price_obj:anyhedge_models.PriceOracleMessage=None):
    """
        Returns `anyhedge_models.PriceOracleMessage` instance if success
        Returns string as error message if fail
    """
    if not isinstance(price_obj, anyhedge_models.PriceOracleMessage):
        price_obj = anyhedge_models.PriceOracleMessage.objects \
            .filter(pubkey=oracle_public_key) \
            .order_by("-message_timestamp") \
            .first()

    if not price_obj:
        return "No price message found"

    if price_obj.pubkey != oracle_public_key:
        return "Oracle public key does not match"

    return price_obj


# ============================================================================= #
# """"""""""""""""""""""""""""""Funding functions"""""""""""""""""""""""""""""" #
# ============================================================================= #

def create_tx_for_funding_utxo(treasury_contract_address:str, satoshis:int):
    treasury_contract = models.TreasuryContract.objects.get(address=treasury_contract_address)
    utxos = get_bch_utxos(treasury_contract_address, satoshis=satoshis)

    if not len(utxos):
        raise Exception("No utxo/s found")

    cashcsript_utxos = [tx_model_to_cashscript(utxo) for utxo in utxos]
    result = ScriptFunctions.constructTreasuryContractTx(dict(
        contractOpts = treasury_contract.contract_opts,
        inputs = cashcsript_utxos,
        outputs = [dict(
            to=treasury_contract.address,
            amount=satoshis,
        )]
    ))

    return result
