import time
import json
import decimal
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from stablehedge.apps import LOGGER
from stablehedge import models
from stablehedge.exceptions import StablehedgeException
from stablehedge.utils.anyhedge import get_latest_oracle_price
from stablehedge.utils.blockchain import (
    test_transaction_accept,
    broadcast_transaction,
)
from stablehedge.utils.transaction import (
    validate_utxo_data,
    utxo_data_to_cashscript,
    tx_model_to_cashscript,
    get_tx_input_hashes,
    satoshis_to_token,
)
from stablehedge.js.runner import ScriptFunctions

from .treasury_contract import (
    get_spendable_sats,
    get_unallocated_reserve_sats,
    find_single_bch_utxo,
    get_bch_utxos,
    save_signature_to_tx,
    get_funding_wif,
    get_funding_wif_address,
    sweep_funding_wif,
)

from anyhedge import models as anyhedge_models
from anyhedge.js.runner import AnyhedgeFunctions
from anyhedge.tasks import parse_contract_liquidity_fee
from anyhedge.utils.liquidity_provider import GeneralProtocolsLP
from anyhedge.utils.liquidity import (
    fund_hedge_position,
    resolve_liquidity_fee,
)
from anyhedge.utils.funding import calculate_funding_amounts
from anyhedge.utils.contract import (
    AnyhedgeException,
    create_contract,
    contract_data_to_obj,
    save_contract_data,
    get_contract_status,
)

from main.tasks import _process_mempool_transaction


GP_LP = GeneralProtocolsLP()
REDIS_STORAGE = settings.REDISKV

# most preimum so far was around 1% for hedge, while 2.5% for short 
# we set 5% for a large margin
MAX_PREMIUM_PCTG = 0.05
HEDGE_FUNDING_NETWORK_FEES = 2500 # sats
SETTLEMENT_SERVICE_FEE = 3000 # sats

DUST_SATS = 546
MINIMUM_BALANCE_FOR_SHORT = DUST_SATS + (DUST_SATS / MAX_PREMIUM_PCTG) + \
                            HEDGE_FUNDING_NETWORK_FEES + \
                            SETTLEMENT_SERVICE_FEE


def get_or_create_short_proposal(treasury_contract_address:str):
    existing_data = get_short_contract_proposal(treasury_contract_address)
    if existing_data:
        return existing_data

    return create_short_proposal(treasury_contract_address)


def create_short_proposal(treasury_contract_address:str, for_multisig=False, cap_tvl:float=0.5):
    LOGGER.info(f"SHORT PROPOSAL | CREATE | {treasury_contract_address}")
    short_proposal_data = short_funds(treasury_contract_address, for_multisig=for_multisig, cap_tvl=cap_tvl)

    data_str = GP_LP.json_parser.dumps(short_proposal_data, indent=2)
    LOGGER.info(f"SHORT PROPOSAL | CREATE |{treasury_contract_address} | {data_str}")

    save_short_proposal_data(
        treasury_contract_address,
        contract_data = short_proposal_data["contract_data"],
        settlement_service = short_proposal_data["settlement_service"],
        funding_amounts = short_proposal_data["funding_amounts"],
        funding_utxo_tx = short_proposal_data["funding_utxo_tx"],
    )

    return short_proposal_data

def save_short_proposal_data(
    treasury_contract_address,
    contract_data=None,
    settlement_service=None,
    funding_amounts=None,
    funding_utxo_tx=None,
):
    timeout = funding_amounts["recalculate_after"]
    ttl = int(timeout - time.time()) - 5 # 5 seconds for margin
    # ttl = None

    short_proposal_data = dict(
        contract_data = contract_data,
        settlement_service = settlement_service,
        funding_amounts = funding_amounts,
        funding_utxo_tx = funding_utxo_tx,
    )
    REDIS_KEY = f"treasury-contract-short-{treasury_contract_address}"

    LOGGER.debug(f"SHORT PROPOSAL | SAVE | {treasury_contract_address} | ttl={ttl}")
    REDIS_STORAGE.set(REDIS_KEY, GP_LP.json_parser.dumps(short_proposal_data), ex=ttl)
    return ttl

def delete_short_proposal_data(treasury_contract_address:str):
    REDIS_KEY = f"treasury-contract-short-{treasury_contract_address}"
    return REDIS_STORAGE.delete(REDIS_KEY)

def get_short_contract_proposal(treasury_contract_address:str, recompile=False):
    treasury_contract = models.TreasuryContract.objects.get(address=treasury_contract_address)

    REDIS_KEY = f"treasury-contract-short-{treasury_contract.address}"
    try:
        data = REDIS_STORAGE.get(REDIS_KEY)
        short_proposal_data = GP_LP.json_parser.loads(data)

        if recompile:
            contract_data = short_proposal_data["contract_data"]
            # there is a recompile check inside that will throw error if address mismatch
            contract_data_to_obj(contract_data)

        return short_proposal_data
    except (TypeError, json.JSONDecodeError):
        return
    except AnyhedgeException as exception:
        if exception.code == AnyhedgeException.ADDRESS_MISMATCH:
            LOGGER.debug(f"SHORT PROPOSAL | ADDRESS MISMATCH | {treasury_contract_address}")
            return
        else:
            raise exception

def update_short_proposal_access_keys(treasury_contract_address:str, pubkey:str="", signature:str=""):
    LOGGER.info(f"SHORT PROPOSAL | ACCESS KEYS | {treasury_contract_address} | {pubkey} | {signature}")
    short_proposal_data = get_short_contract_proposal(treasury_contract_address, recompile=True)
    contract_data = short_proposal_data["contract_data"]
    settlement_service = short_proposal_data["settlement_service"]

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
    if contract_data2["address"] != contract_data["address"]:
        raise AnyhedgeException("Address mismatch", code=AnyhedgeException.ADDRESS_MISMATCH)
    else:
        contract_data = contract_data2

    if pubkey == short_pubkey:
        settlement_service["short_signature"] = signature
    else:
        settlement_service["long_signature"] = signature

    short_proposal_data["contract_data"] = contract_data
    short_proposal_data["settlement_service"] = settlement_service
    save_short_proposal_data(
        treasury_contract_address,
        **short_proposal_data,
    )

    data_str = GP_LP.json_parser.dumps(short_proposal_data, indent=2)
    LOGGER.debug(f"SHORT PROPOSAL | ACCESS KEYS | {treasury_contract_address} | {data_str}")

    return short_proposal_data

def refetch_short_proposal_contract_data(treasury_contract_address:str, pubkey="", signature="", save=False):
    short_proposal_data = get_short_contract_proposal(treasury_contract_address, recompile=True)

    contract_data = short_proposal_data["contract_data"]
    settlement_service = short_proposal_data["settlement_service"]

    if not pubkey or not signature:
        parameters = contract_data["parameters"]
        if settlement_service.get("short_signature"):
            signature = settlement_service["short_signature"]
            pubkey = parameters["shortMutualRedeemPublicKey"]
        elif settlement_service.get("long_signature"):
            signature = settlement_service["long_signature"]
            pubkey = parameters["longMutualRedeemPublicKey"]

    contract_data = get_contract_status(
        contract_data["address"],
        pubkey,
        signature,
        settlement_service_scheme=settlement_service["scheme"],
        settlement_service_domain=settlement_service["host"],
        settlement_service_port=settlement_service["port"],
        authentication_token=settlement_service.get("auth_token", None),
    )

    short_proposal_data["contract_data"] = contract_data
    save_short_proposal_data(
        treasury_contract_address,
        **short_proposal_data,
    )

    return short_proposal_data


def short_funds(treasury_contract_address:str, for_multisig=False, cap_tvl:float=0.5):
    treasury_contract = models.TreasuryContract.objects.get(address=treasury_contract_address)
    balance_data = get_spendable_sats(treasury_contract_address)
    spendable_sats = balance_data["spendable"]
    LOGGER.debug(f"SHORT PROPOSAL | BALANCE | {treasury_contract_address} | {balance_data}")

    shortable_sats = (spendable_sats - HEDGE_FUNDING_NETWORK_FEES - SETTLEMENT_SERVICE_FEE) * (1-MAX_PREMIUM_PCTG)

    if cap_tvl:
        tvl_data = _get_tvl_sats(treasury_contract_address)
        tvl_sats = int(tvl_data["total"])
        capped_tvl_sats = tvl_sats * cap_tvl
        capped_tvl_sats -= int(tvl_data.get("in_short") or 0)
        shortable_sats = min(capped_tvl_sats, shortable_sats)
        if shortable_sats <= 0:
            raise StablehedgeException(
                f"Total shorted value is more than x{cap_tvl} of TVL",
                code="tvl-cap-reached",
            )

    try:
        duration_seconds = treasury_contract.short_position_rule.target_duration
    except models.TreasuryContract.short_position_rule.RelatedObjectDoesNotExist:
        duration_seconds = 86_400 # seconds = 1 day

    create_result = create_short_contract(
        treasury_contract_address,
        satoshis=shortable_sats,
        low_liquidation_multiplier = 0.5,
        high_liquidation_multiplier = 2.0,
        duration_seconds = duration_seconds,
    )

    if "contract_data" not in create_result:
        raise StablehedgeException(create_result.get("error"), code="create_failed")

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

    data_str = GP_LP.json_parser.dumps(contract_proposal_data, indent=2)
    LOGGER.debug(f"SHORT PROPOSAL | PROPOSAL DATA | {treasury_contract_address} | {data_str}")

    service_fee_estimate = GP_LP.estimate_service_fee(
        contract_proposal_data,
        settlement_service=settlement_service,
    )
    proposal_data = GP_LP.propose_contract(contract_proposal_data)

    data_str = GP_LP.json_parser.dumps(proposal_data, indent=2)
    LOGGER.debug(f"SHORT PROPOSAL | PROPOSAL RESULT | {treasury_contract_address} | {data_str}")

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

    if sats_to_fund > spendable_sats:
        LOGGER.debug(
            f"SHORT PROPOSAL | INSUFFICIENT FUNDS | {treasury_contract_address}"
            f" | sats_to_fund={sats_to_fund} | spendable_sats={spendable_sats}"
            f" | shortable_sats={shortable_sats}"
        )
        raise StablehedgeException("Insufficient funds for funding", code="insufficient-funds")

    funding_utxo_tx = create_tx_for_funding_utxo(
        treasury_contract_address,
        int(sats_to_fund),
        for_multisig=for_multisig,
    )

    return dict(
        contract_data = contract_data,
        settlement_service = settlement_service,
        funding_amounts = funding_amounts,
        funding_utxo_tx = funding_utxo_tx,
    )


def _get_tvl_sats(treasury_contract_address:str):
    result = {}
    total = 0

    balance_data = get_spendable_sats(treasury_contract_address)
    spendable = decimal.Decimal(balance_data["spendable"])
    result["satoshis"] = spendable
    total += spendable

    short_value_data = get_total_short_value(treasury_contract_address)
    short_value_sats = decimal.Decimal(short_value_data["satoshis"])
    result["in_short"] = short_value_sats
    total += short_value_sats

    unallocated_reserve_satoshis = None
    unalloc_reserve_data = get_unallocated_reserve_sats(treasury_contract_address)
    if "spendable" in unalloc_reserve_data:
        unallocated_reserve_satoshis = decimal.Decimal(unalloc_reserve_data["spendable"])
        total += unallocated_reserve_satoshis
    result["unallocated_reserve_satoshis"] = unallocated_reserve_satoshis

    redeemable = models.RedemptionContract.objects \
        .annotate_redeemable() \
        .filter(treasury_contract__address=treasury_contract_address) \
        .values_list("redeemable", flat=True).first()
    if redeemable is not None:
        redeemable = decimal.Decimal(redeemable)
        result["redeemable"] = redeemable
        total += redeemable

    result["total"] = total
    return result


def create_short_contract(
    treasury_contract_address:str,
    price_obj:anyhedge_models.PriceOracleMessage=None,
    satoshis:int=0,
    low_liquidation_multiplier:float=0.5,
    high_liquidation_multiplier:float=2.0,
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
    LOGGER.debug(f"SHORT PROPOSAL | SETTLEMENT SERVICE | {GP_LP.json_parser.dumps(settlement_service, indent=2)}")

    if oracle_public_key not in liquidity_info["liquidityParameters"]:
        return dict(success=False, error="Oracle is not supported by liquidity provider")

    constraints = liquidity_info["liquidityParameters"][oracle_public_key]
    LOGGER.debug(f"SHORT PROPOSAL | CONSTRAINTS | {GP_LP.json_parser.dumps(constraints, indent=2)}")
    intent = GP_LP.fit_intent_to_constraints(
        satoshis=satoshis,
        low_liquidation_multiplier = low_liquidation_multiplier,
        high_liquidation_multiplier = high_liquidation_multiplier,
        duration_seconds = duration_seconds, # 1 day
        constraints=constraints,
        start_price=price_obj.price_value,
        is_simple_hedge=False,
    )
    LOGGER.debug(f"SHORT PROPOSAL | INTENT | {GP_LP.json_parser.dumps(intent, indent=2)}")

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
    short_address = treasury_contract.address

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

    LOGGER.debug(f"SHORT PROPOSAL | CONTRACT | {GP_LP.json_parser.dumps(contract_data, indent=2)}")
    return dict(success=True, contract_data=contract_data, settlement_service=settlement_service)

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

    if price_obj.message_timestamp < (timezone.now() - timezone.timedelta(seconds=120)):
        return "Price is too old"

    if not price_obj:
        return "No price message found"

    if price_obj.pubkey != oracle_public_key:
        return "Oracle public key does not match"

    return price_obj


# ============================================================================= #
# """"""""""""""""""""""""""""""Funding functions"""""""""""""""""""""""""""""" #
# ============================================================================= #

def create_tx_for_funding_utxo(treasury_contract_address:str, satoshis:int, for_multisig=False):
    treasury_contract = models.TreasuryContract.objects.get(address=treasury_contract_address)
    # added 1000 to ensure change amount dont end up as transaction fee due to min dust
    utxos = get_bch_utxos(treasury_contract_address, satoshis=satoshis + 1000)

    if not len(utxos):
        raise Exception("No utxo/s found")

    inputs = [tx_model_to_cashscript(utxo) for utxo in utxos]
    funding_address = get_funding_wif_address(treasury_contract.address, token=False)
    outputs = [dict(
        to=funding_address,
        amount=satoshis,
    )]

    if not for_multisig:
        token_data = dict(category=treasury_contract.auth_token_id, amount=0, nft=dict(capability="none", commitment="0" * 40))
        inputs.insert(1, dict(txid="0" * 64, vout=-1, satoshis= -1, token=token_data))
        outputs.insert(1, dict(to="", amount=0, token=token_data))

    result = ScriptFunctions.constructTreasuryContractTx(dict(
        locktime = 0,
        multiSig = for_multisig,
        contractOpts = treasury_contract.contract_opts,
        inputs = inputs,
        outputs = outputs,
    ))

    result["is_multisig"] = for_multisig
    result["locktime"] = 0
    result["funding_utxo_index"] = 0

    return result


def update_short_proposal_funding_utxo_tx_sig(treasury_contract_address:str, sig:list, sig_index:int=0):
    LOGGER.info(f"SHORT PROPOSAL | FUNDING UTXO TX SIG | {treasury_contract_address} | {sig_index} | {sig}")
    treasury_contract = models.TreasuryContract.objects.get(address=treasury_contract_address)

    short_proposal_data = get_short_contract_proposal(treasury_contract_address, recompile=False)
    if not short_proposal_data["funding_utxo_tx"].get("is_multisig"):
        raise StablehedgeException("Transaction is not for multisig", code="invalid-tx-type")

    short_proposal_data["funding_utxo_tx"] = save_signature_to_tx(
        treasury_contract,
        short_proposal_data["funding_utxo_tx"],
        sig,
        int(sig_index),
    )
    save_short_proposal_data(
        treasury_contract_address,
        **short_proposal_data,
    )

    data_str = GP_LP.json_parser.dumps(short_proposal_data, indent=2)
    LOGGER.debug(f"SHORT PROPOSAL | FUNDING UTXO TX SIG | {treasury_contract_address} | {data_str}")

    return short_proposal_data


def update_short_proposal_funding_utxo_tx_auth_key(treasury_contract_address:str, utxo_data:dict):
    LOGGER.info(f"SHORT PROPOSAL | FUNDING UTXO TX AUTH KEY | {treasury_contract_address} | {utxo_data}")

    utxo_data_validation = validate_utxo_data(
        utxo_data,
        require_cashtoken=True,
        require_nft_token=True,
        require_unlock=True,
        raise_error=False,
    )
    if isinstance(utxo_data_validation, str):
        raise StablehedgeException(f"Invalid utxo: {utxo_data_validation}", code="invalid-utxo")

    treasury_contract = models.TreasuryContract.objects.get(address=treasury_contract_address)

    short_proposal_data = get_short_contract_proposal(treasury_contract_address, recompile=False)
    funding_utxo_tx = short_proposal_data["funding_utxo_tx"]

    if funding_utxo_tx.get("is_multisig"):
        raise StablehedgeException("Transaction is for multisig", code="invalid-tx-type")

    if treasury_contract.auth_token_id != funding_utxo_tx["inputs"][1]["token"]["category"]:
        raise StablehedgeException("Auth key input's token category does not match", code="invalid-authkey")

    if treasury_contract.auth_token_id != utxo_data["category"]:
        raise StablehedgeException("Utxo token category invalid", code="invalid-authkey")

    cashscript_utxo = utxo_data_to_cashscript(utxo_data)
    funding_utxo_tx["inputs"][1] = cashscript_utxo
    funding_utxo_tx["outputs"][1] = dict(
        to=cashscript_utxo["lockingBytecode"],
        amount=cashscript_utxo["satoshis"],
        token=cashscript_utxo["token"],
    )
    short_proposal_data["funding_utxo_tx"] = funding_utxo_tx
    save_short_proposal_data(
        treasury_contract_address,
        **short_proposal_data,
    )

    data_str = GP_LP.json_parser.dumps(short_proposal_data, indent=2)
    LOGGER.debug(f"SHORT PROPOSAL | FUNDING UTXO TX AUTH KEY | {treasury_contract_address} | {data_str}")
    return short_proposal_data


def build_short_proposal_funding_utxo_tx(treasury_contract_address:str):
    short_proposal_data = get_short_contract_proposal(treasury_contract_address, recompile=False)
    funding_utxo_tx = short_proposal_data["funding_utxo_tx"]
    treasury_contract = models.TreasuryContract.objects.get(address=treasury_contract_address)

    funding_utxo_tx_str = GP_LP.json_parser.dumps(funding_utxo_tx, indent=2)
    LOGGER.debug(f"SHORT PROPOSAL | FUNDING UTXO TX BUILD | {treasury_contract_address} | {funding_utxo_tx_str}")

    if funding_utxo_tx.get("is_multisig"):
        build_result = ScriptFunctions.unlockTreasuryContractWithMultiSig(dict(
            contractOpts=treasury_contract.contract_opts,
            sig1=funding_utxo_tx["sig1"],
            sig2=funding_utxo_tx["sig2"],
            sig3=funding_utxo_tx["sig3"],
            locktime=funding_utxo_tx.get("locktime") or 0,
            inputs=funding_utxo_tx["inputs"],
            outputs=funding_utxo_tx["outputs"],
        ))
    else:
        build_result = ScriptFunctions.unlockTreasuryContractWithNft(dict(
            contractOpts=treasury_contract.contract_opts,
            keepGuarded=False,
            locktime=funding_utxo_tx.get("locktime") or 0,
            inputs=funding_utxo_tx["inputs"],
            outputs=funding_utxo_tx["outputs"],
        ))

    if not build_result["success"]:
        error_msg = build_result.get("success") or "Failed to build transaction"
        raise StablehedgeException(error_msg, code="build_failed")

    tx_hex = build_result["tx_hex"]
    valid_tx, error_or_txid = test_transaction_accept(tx_hex)
    LOGGER.info(f"SHORT PROPOSAL | FUNDING UTXO TX BUILD | {treasury_contract_address} | {error_or_txid} | {tx_hex}")

    if not valid_tx:
        raise StablehedgeException("Invalid transaction", code=error_or_txid)

    return dict(tx_hex=tx_hex, txid=error_or_txid)


def complete_short_proposal_funding_txs(treasury_contract_address:str):
    LOGGER.info(f"SHORT PROPOSAL | FUNDING TXS BUILD | {treasury_contract_address}")
    short_proposal_data = get_short_contract_proposal(treasury_contract_address, recompile=False)

    data_str = GP_LP.json_parser.dumps(short_proposal_data, indent=2)
    LOGGER.debug(f"SHORT PROPOSAL | FUNDING TXS BUILD | {treasury_contract_address} | {data_str}")

    contract_data = short_proposal_data["contract_data"]
    settlement_service = short_proposal_data["settlement_service"]
    funding_utxo_tx = short_proposal_data["funding_utxo_tx"]

    if funding_utxo_tx.get("txid"):
        funding_utxo_txid = funding_utxo_tx["txid"]
        funding_utxo_tx_hex = None
    else:
        build_result = build_short_proposal_funding_utxo_tx(treasury_contract_address)
        funding_utxo_txid = build_result["txid"]
        funding_utxo_tx_hex = build_result["tx_hex"]

    funding_utxo_index = int(funding_utxo_tx.get("funding_utxo_index", 0))
    funding_utxo_sats = int(funding_utxo_tx["outputs"][funding_utxo_index]["amount"])

    proxy_funding_wif = get_funding_wif(treasury_contract_address)
    funding_utxo = dict(
        txid=funding_utxo_txid,
        vout=funding_utxo_index,
        satoshis=funding_utxo_sats,
        # wif=proxy_funding_wif,
        # hashType=1 | 128, # SIGHASH_ALL | SIGHASH_ANYONECANPAY
    )

    create_outputs_result = AnyhedgeFunctions.createFundingTransactionOutputs(contract_data)
    funding_outputs = create_outputs_result["outputs"]
    LOGGER.debug(f"FUNDING OUTPUTS | {GP_LP.json_parser.dumps(funding_outputs, indent=2)}")

    # proxy_funding_tx = dict(
    #     locktime=0,
    #     inputs=[funding_utxo],
    #     outputs=funding_outputs,
    # )

    funding_proposal_signature = AnyhedgeFunctions.signFundingUtxo(
        contract_data, funding_utxo, proxy_funding_wif,
    )
    script_sig = funding_proposal_signature["signature"]
    script_sig_pubkey = funding_proposal_signature["publicKey"]
    input_tx_hashes = [inp["txid"] for inp in funding_utxo_tx["inputs"]]

    funding_proposal = dict(
        txHash=funding_utxo["txid"],
        txIndex=funding_utxo["vout"],
        txValue=funding_utxo["satoshis"],
        scriptSig=script_sig,
        # publicKey=contract_data["parameters"]["shortMutualRedeemPublicKey"],
        publicKey=script_sig_pubkey,
        inputTxHashes=input_tx_hashes,
    )

    position = contract_data["metadata"]["takerSide"]
    if position == "long":
        funding_proposal["publicKey"] = contract_data["parameters"]["longMutualRedeemPublicKey"]

    funding_proposal_str = GP_LP.json_parser.dumps(funding_proposal, indent=2)
    LOGGER.info(f"FUNDING TXS | {treasury_contract_address} | funding_proposal = {funding_proposal_str} | funding_utxo_tx = {funding_utxo_tx_hex}")

    return dict(
        # short_proposal_data=short_proposal_data,
        funding_utxo_tx_hex=funding_utxo_tx_hex,
        funding_proposal=funding_proposal,   
    )

def complete_short_proposal(treasury_contract_address:str):
    treasury_contract = models.TreasuryContract.objects.get(address=treasury_contract_address)
    short_proposal_data = get_short_contract_proposal(treasury_contract_address, recompile=False)

    if not short_proposal_data:
        raise StablehedgeException("No short proposal")

    data_str = GP_LP.json_parser.dumps(short_proposal_data, indent=2)
    LOGGER.info(f"SHORT PROPOSAL | COMPLETE | {treasury_contract_address} | {data_str}")

    contract_data = short_proposal_data["contract_data"]
    settlement_service = short_proposal_data["settlement_service"]

    funding_txs_data = complete_short_proposal_funding_txs(treasury_contract_address)

    funding_utxo_tx_hex = funding_txs_data["funding_utxo_tx_hex"]
    funding_proposal = funding_txs_data["funding_proposal"]

    if funding_utxo_tx_hex:
        success, error_or_txid = broadcast_transaction(funding_utxo_tx_hex)
        if not success:
            raise StablehedgeException("Invalid funding utxo tx", code="invalid_transaction")
        short_proposal_data["funding_utxo_tx"]["txid"] = error_or_txid
        save_short_proposal_data(
            treasury_contract_address,
            **short_proposal_data,
        )

    return complete_short_proposal_funding(
        treasury_contract_address,
        contract_data,
        settlement_service,
        funding_proposal,
    )


def complete_short_proposal_funding(
    treasury_contract_address:str,
    contract_data:dict,
    settlement_service:dict,
    funding_proposal:dict,
):
    oracle_message_sequence = GP_LP.contract_data_to_proposal(contract_data)["contractStartingOracleMessageSequence"]
    hedge_pos_obj = save_contract_data(contract_data, settlement_service_data=settlement_service)
    funding_response = fund_hedge_position(
        contract_data,
        funding_proposal,
        oracle_message_sequence,
        position=contract_data["metadata"]["takerSide"],
    )

    try:
        data_str = GP_LP.json_parser.dumps(funding_response, indent=2)
        LOGGER.info(f"GP LP FUNDING RESPONSE | {treasury_contract_address} | {data_str}")
    except Exception as exception:
        LOGGER.exception(exception)

    if not funding_response.get("success"):
        try:
            sweep_funding_wif(treasury_contract_address)
        except StablehedgeException:
            pass
        raise AnyhedgeException(funding_response["error"], code="funding_error")

    hedge_pos_obj.funding_tx_hash = funding_response["fundingTransactionHash"]
    hedge_pos_obj.save()

    # encasing the following steps in try catch since
    # previous 2 steps must complete & not rollback db transactions; and
    # the following steps are not that critical
    try:
        parse_contract_liquidity_fee.delay(hedge_pos_obj.address)
    except Exception as exception:
        LOGGER.exception(exception)

    try:
        delete_short_proposal_data(treasury_contract_address)
    except Exception as exception:
        LOGGER.exception(exception)

    try:
        _process_mempool_transaction(hedge_pos_obj.funding_tx_hash, force=True)
    except Exception as exception:
        LOGGER.exception(exception)

    return hedge_pos_obj

@transaction.atomic
def place_short_proposal(
    treasury_contract_address:str="",
    short_contract_address:str="",
    settlement_service:dict=None,
    funding_utxo_tx_hex:str="",
):
    settlement_service_str = GP_LP.json_parser.dumps(settlement_service, indent=2)
    LOGGER.info(f"SHORT | {treasury_contract_address} | address={short_contract_address} | settlement_service = {settlement_service_str} | {funding_utxo_tx_hex}")

    treasury_contract = models.TreasuryContract.objects.get(address=treasury_contract_address)
    contract_data = get_contract_status(
        short_contract_address,
        settlement_service["pubkey"],
        settlement_service["short_signature"],
        settlement_service_scheme=settlement_service["scheme"],
        settlement_service_domain=settlement_service["host"],
        settlement_service_port=settlement_service["port"],
        authentication_token=settlement_service.get("auth_token", None),
    )
    contract_data_str = GP_LP.json_parser.dumps(contract_data, indent=2)
    LOGGER.info(f"SHORT | {treasury_contract_address} | contract_data={contract_data}")

    funding_amounts = calculate_funding_amounts(
        contract_data,
        position=contract_data["metadata"]["takerSide"],
    )
    funding_amounts_str = GP_LP.json_parser.dumps(funding_amounts, indent=2)
    LOGGER.info(f"SHORT | {treasury_contract_address} | funding_amounts={funding_amounts_str}")

    valid_tx, error_or_txid = test_transaction_accept(funding_utxo_tx_hex)
    if not valid_tx:
        raise StablehedgeException("Invalid funding utxo transaction", code="invalid-funding-utxo-tx")

    proxy_funder_address = get_funding_wif_address(treasury_contract_address)
    proxy_funder_wif = get_funding_wif(treasury_contract_address)
    funding_utxo_tx = NODE.BCH.build_tx_from_hex(funding_utxo_tx_hex)

    funding_utxo_tx_str = GP_LP.json_parser.dumps(funding_utxo_tx, indent=2)
    LOGGER.info(f"SHORT | {treasury_contract_address} | proxy_funder_address={proxy_funder_address} | funding_utxo_tx={funding_utxo_tx_str}")

    if funding_utxo_tx["vout"][0]["address"] != proxy_funder_address:
        raise StablehedgeException("Invalid funding utxo address", code="invalid-funding-utxo-address")

    if funding_utxo_tx["vout"][0]["value"] != funding_amounts["short"]:
        raise StablehedgeException(
            f"Invalid funding utxo amount, got {funding_utxo_tx['vout'][0]['value']}, expected {funding_amounts['short']}",
            code="invalid-funding-utxo-amount",
        )

    funding_utxo = dict(
        txid=error_or_txid,
        vout=0,
        satoshis=funding_utxo_tx["vout"][0]["value"],
        # wif=proxy_funding_wif,
        # hashType=1 | 128, # SIGHASH_ALL | SIGHASH_ANYONECANPAY
    )
    funding_proposal_signature = AnyhedgeFunctions.signFundingUtxo(
        contract_data, funding_utxo, proxy_funder_wif,
    )

    script_sig = funding_proposal_signature["signature"]
    script_sig_pubkey = funding_proposal_signature["publicKey"]
    input_tx_hashes = [inp["txid"] for inp in funding_utxo_tx["vin"]]

    funding_proposal = dict(
        txHash=funding_utxo["txid"],
        txIndex=funding_utxo["vout"],
        txValue=funding_utxo["satoshis"],
        scriptSig=script_sig,
        # publicKey=contract_data["parameters"]["shortMutualRedeemPublicKey"],
        publicKey=script_sig_pubkey,
        inputTxHashes=input_tx_hashes,
    )
    position = contract_data["metadata"]["takerSide"]
    if position == "long":
        funding_proposal["publicKey"] = contract_data["parameters"]["longMutualRedeemPublicKey"]

    funding_proposal_str = GP_LP.json_parser.dumps(funding_proposal, indent=2)
    LOGGER.info(f"SHORT | {treasury_contract_address} | funding_proposal={funding_proposal_str}")

    oracle_message_sequence = GP_LP.contract_data_to_proposal(contract_data)["contractStartingOracleMessageSequence"]
    hedge_pos_obj = save_contract_data(contract_data, settlement_service_data=settlement_service)

    """
    - `broadcast_transaction` and `fund_hedge_position` are made last
        since they involve broadcasting transactions
    - Succeeding steps must not cause errors or atleast fail silently to not lose the saved hedge position data
    """
    success, error_or_txid = broadcast_transaction(funding_utxo_tx_hex)
    if not success:
        raise StablehedgeException("Funding utxo tx failed", code="funding-utxo-tx-failed")

    funding_response = fund_hedge_position(
        contract_data,
        funding_proposal,
        oracle_message_sequence,
        position=contract_data["metadata"]["takerSide"],
    )

    try:
        data_str = GP_LP.json_parser.dumps(funding_response, indent=2)
        LOGGER.info(f"GP LP FUNDING RESPONSE | {treasury_contract_address} | {data_str}")
    except Exception as exception:
        LOGGER.exception(exception)

    if not funding_response.get("success"):
        sweep_funding_wif(treasury_contract_address)
        raise AnyhedgeException(funding_response["error"], code="funding_error")

    hedge_pos_obj.funding_tx_hash = funding_response["fundingTransactionHash"]
    hedge_pos_obj.save()

    # encasing the following steps in try catch since
    # previous 2 steps must complete & not rollback db transactions; and
    # the following steps are not that critical
    try:
        parse_contract_liquidity_fee.delay(hedge_pos_obj.address)
    except Exception as exception:
        LOGGER.exception(exception)

    try:
        _process_mempool_transaction(hedge_pos_obj.funding_tx_hash, force=True)
    except Exception as exception:
        LOGGER.exception(exception)

    return hedge_pos_obj

# ============================================================================= #
# """""""""""""""""""""""""""""""""Monitoring"""""""""""""""""""""""""""""""""" #
# ============================================================================= #
def get_ongoing_short_positions(treasury_contract_address:str):
    return anyhedge_models.HedgePosition.objects.filter(
        short_address=treasury_contract_address,
        funding_tx_hash__isnull=False,
        settlements__isnull=True,
    )

def get_total_short_value(treasury_contract_address:str):
    ongoing_short_positions = get_ongoing_short_positions(treasury_contract_address)
    if ongoing_short_positions.filter(metadata__total_short_funding_sats__isnull=True).exists():
        for short_position in ongoing_short_positions:
            resolve_liquidity_fee(short_position, hard_update=True)

    short_position_values = ongoing_short_positions \
        .annotate(short_funding_sats = F("metadata__total_short_funding_sats")) \
        .values(
            "start_price",
            "short_funding_sats",
        )

    total_sats = decimal.Decimal(0)
    total_unit_value = decimal.Decimal(0)
    for data in short_position_values:
        funding_sats = decimal.Decimal(data["short_funding_sats"])
        start_price = decimal.Decimal(data["start_price"])
        token_units = satoshis_to_token(funding_sats, start_price)

        total_sats += funding_sats
        total_unit_value += token_units

    return dict(
        count=len(short_position_values),
        satoshis=total_sats,
        unit_value=total_unit_value,
    )
