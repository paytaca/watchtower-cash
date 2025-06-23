import time
import json
from celery import shared_task
from django.conf import settings

from stablehedge import models
from stablehedge.apps import LOGGER
from stablehedge.js.runner import ScriptFunctions
from stablehedge.functions.anyhedge import (
    AnyhedgeException,
    StablehedgeException,
    MINIMUM_BALANCE_FOR_SHORT,
    get_short_contract_proposal,
    create_short_proposal,
    create_short_contract,
    update_short_proposal_access_keys,
    update_short_proposal_funding_utxo_tx_sig,
    complete_short_proposal,
    complete_short_proposal_funding,
    _get_tvl_sats,
)
from stablehedge.functions.treasury_contract import (
    get_spendable_sats,
    get_wif_for_short_proposal,
    build_or_find_funding_utxo,
)
from stablehedge.functions.market import transfer_treasury_funds_to_redemption_contract
from stablehedge.utils.blockchain import broadcast_transaction
from stablehedge.utils.wallet import wif_to_pubkey
from stablehedge.utils.transaction import extract_unlocking_script

from anyhedge.utils.liquidity_provider import GeneralProtocolsLP
from anyhedge.utils.contract import contract_data_to_obj
from anyhedge.utils.contract import get_contract_status


REDIS_STORAGE = settings.REDISKV
GP_LP = GeneralProtocolsLP()

_TASK_TIME_LIMIT = 300 # 5 minutes
_QUEUE_TREASURY_CONTRACT = "stablehedge__treasury_contract"


def check_and_short_funds(
    treasury_contract_address:str,
    min_sats:int=10 ** 8,
    background_task:bool=False,
):
    balance_data = get_spendable_sats(treasury_contract_address)
    spendable = balance_data["spendable"]
    
    actual_min_sats = max(min_sats, MINIMUM_BALANCE_FOR_SHORT)
    if not spendable or spendable < actual_min_sats:
        return dict(success=True, message="Balance not met", min_sats=actual_min_sats, spendable=spendable)

    LOGGER.debug(f"SHORT PROPOSAL | {treasury_contract_address} | ATTEMPT RUN")
    if background_task:
        task = short_treasury_contract_funds.delay(treasury_contract_address)
        result = dict(success=True, task_id=task.id)
    else:
        result = short_treasury_contract_funds(treasury_contract_address)

    return result
    
@shared_task(queue=_QUEUE_TREASURY_CONTRACT)
def check_treasury_contract_short():
    results = []
    for treasury_contract in models.TreasuryContract.objects.filter():
        try:
            min_sats = treasury_contract.short_position_rule.target_satoshis
        except models.TreasuryContract.short_position_rule.RelatedObjectDoesNotExist:
            min_sats = 10 ** 8

        result = check_and_short_funds(
            treasury_contract.address,
            min_sats=min_sats,
            background_task=True,
        )

        results.append(
            (treasury_contract.address, result),
        )

    return results


@shared_task(queue=_QUEUE_TREASURY_CONTRACT, time_limit=_TASK_TIME_LIMIT)
def short_treasury_contract_funds(treasury_contract_address:str):
    version = models.TreasuryContract.objects \
        .filter(address=treasury_contract_address) \
        .values_list("version", flat=True) \
        .first()

    if version in [models.TreasuryContract.Version.V2, models.TreasuryContract.Version.V3]:
        return short_v2_treasury_contract_funds(treasury_contract_address)
    return short_v1_treasury_contract_funds(treasury_contract_address)


@shared_task(queue=_QUEUE_TREASURY_CONTRACT, time_limit=_TASK_TIME_LIMIT)
def short_v1_treasury_contract_funds(treasury_contract_address:str):
    REDIS_KEY = f"treasury-contract-short-pos-task-{treasury_contract_address}"
    if REDIS_STORAGE.exists(REDIS_KEY):
        return dict(success=False, error="Task key in use")

    LOGGER.info(f"SHORT TREAURY CONTRACT | {treasury_contract_address}")
    try:
        raise Exception("BLOCK")
        REDIS_STORAGE.set(REDIS_KEY, "1", ex=120)

        treasury_contract = models.TreasuryContract.objects.filter(address=treasury_contract_address).first()
        if not treasury_contract:
            return dict(success=False, error="Treasury contract not found")

        # wif used for placing short positions
        # must the wif of treasury contract's pubkey1
        wifs = get_wif_for_short_proposal(treasury_contract)
        if len(wifs) < 3:
            return dict(success=False, error="Not enough private keys found")

        wif = wifs[0]
        wif_pubkey = wif_to_pubkey(wif)
        if wif_pubkey != treasury_contract.pubkey1:
            return dict(success=False, error="WIF used does not match pubkey1")

        short_proposal = get_short_contract_proposal(treasury_contract_address)
        try:
            create_new = not short_proposal["funding_utxo_tx"]["is_multisig"]
        except (KeyError, TypeError):
            create_new = True

        if create_new:
            short_proposal = create_short_proposal(treasury_contract_address, for_multisig=True)
            LOGGER.debug(f"SHORT PROPOSAL | {treasury_contract_address} | NEW | SLEEPING FOR 5 SEC TO PREVENT LP RATE LIMIT")
            time.sleep(5)

        contract_address = short_proposal["contract_data"]["address"]

        funding_amounts = short_proposal["funding_amounts"]
        liquidity_fee = funding_amounts["liquidity_fee"]
        settlement_service_fee = funding_amounts["liquidity_fee"]
        total_lp_fee = liquidity_fee + settlement_service_fee
        sats_to_fund = funding_amounts["satoshis_to_fund"]

        MAX_LP_FEE_PCTG = 0.05
        total_lp_fee_pctg = total_lp_fee / sats_to_fund
        if MAX_LP_FEE_PCTG < total_lp_fee_pctg:
            return dict(
                success=True, error="Liquidity fee too large",
                funding_amount=sats_to_fund, liquidity_provider_fee=total_lp_fee,
            )

        access_key_sign_result = ScriptFunctions.schnorrSign(dict(
            message=contract_address, wif=wif,
        ))
        data_str = GP_LP.json_parser.dumps(access_key_sign_result, indent=2)
        LOGGER.debug(f"SHORT PROPOSAL | ACCESS KEY | {treasury_contract_address} | {data_str}")

        if not access_key_sign_result["success"]:
            return dict(
                success=False, code="access-key-error",
                error=access_key_sign_result.get("error"),
            )

        short_proposal = update_short_proposal_access_keys(
            treasury_contract_address,
            pubkey=wif_pubkey,
            signature=access_key_sign_result["signature"],
        )

        funding_utxo_tx = short_proposal["funding_utxo_tx"]

        for index, _wif in enumerate(wifs[:3]):
            signatures = ScriptFunctions.signMutliSigTx(dict(
                contractOpts=treasury_contract.contract_opts,
                wif=_wif,
                locktime=0,
                inputs=funding_utxo_tx["inputs"],
                outputs=funding_utxo_tx["outputs"],
            ))
            update_short_proposal_funding_utxo_tx_sig(treasury_contract_address, signatures, index + 1)
            update_short_proposal_funding_utxo_tx_sig(treasury_contract_address, signatures, index + 1)
            update_short_proposal_funding_utxo_tx_sig(treasury_contract_address, signatures, index + 1)

        hedge_pos_obj = complete_short_proposal(treasury_contract_address)
        return dict(success=True, address=hedge_pos_obj.address)
    except (AnyhedgeException, StablehedgeException) as error:
        return dict(success=False, error=str(error), code=error.code)
    finally:
        REDIS_STORAGE.delete(REDIS_KEY)


@shared_task(queue=_QUEUE_TREASURY_CONTRACT, time_limit=_TASK_TIME_LIMIT)
def short_v2_treasury_contract_funds(treasury_contract_address:str):
    REDIS_KEY = f"treasury-contract-short-pos-task-{treasury_contract_address}"
    if REDIS_STORAGE.exists(REDIS_KEY):
        return dict(success=False, error="Task key in use")

    treasury_contract = models.TreasuryContract.objects.filter(address=treasury_contract_address).first()
    if not treasury_contract:
        return dict(success=False, error="Treasury contract not found")
    elif treasury_contract.version not in [models.TreasuryContract.Version.V2, models.TreasuryContract.Version.V3]:
        return dict(success=False, error="Treasury contract not v2 or v3")

    LOGGER.info(f"SHORT TREAURY CONTRACT | {treasury_contract_address}")

    try:
        REDIS_STORAGE.set(REDIS_KEY, "1", ex=120)

        balance_data = get_spendable_sats(treasury_contract_address)

        MAX_PREMIUM_PCTG = 0.05
        HEDGE_FUNDING_NETWORK_FEES = 2500 # sats
        SETTLEMENT_SERVICE_FEE = 3000 # sats

        spendable_sats = balance_data["spendable"]
        shortable_sats = (spendable_sats - HEDGE_FUNDING_NETWORK_FEES - SETTLEMENT_SERVICE_FEE) * (1-MAX_PREMIUM_PCTG)

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
            raise StablehedgeException(create_result)
        
        contract_data = create_result["contract_data"]
        settlement_service = create_result["settlement_service"]

        contract_data_to_obj(contract_data)

        contract_proposal_data = GP_LP.contract_data_to_proposal(contract_data)
        proposal_data = GP_LP.propose_contract(contract_proposal_data)
        data_str = GP_LP.json_parser.dumps(proposal_data, indent=2)
        LOGGER.debug(f"SHORT | PROPOSAL | {treasury_contract_address} | {data_str}")

        wifs = get_wif_for_short_proposal(treasury_contract)
        short_pubkey = contract_data["parameters"]["shortMutualRedeemPublicKey"]
        wif = None
        for _wif in wifs:
            pubkey = wif_to_pubkey(_wif)
            if pubkey == short_pubkey:
                wif = _wif
                break
    
        if not wif:
            raise StablehedgeException("WIF not found for short position pubkey")

        access_key_sign_result = ScriptFunctions.schnorrSign(dict(
            message=contract_data["address"], wif=wif,
        ))
        data_str = GP_LP.json_parser.dumps(access_key_sign_result, indent=2)
        LOGGER.debug(f"SHORT | ACCESS KEY | {treasury_contract_address} | {data_str}")

        if not access_key_sign_result["success"]:
            return dict(
                success=False, code="access-key-error",
                error=access_key_sign_result.get("error"),
            )

        settlement_service["short_signature"] = access_key_sign_result["signature"]
        contract_data2 = get_contract_status(
            contract_data["address"],
            short_pubkey,
            settlement_service["short_signature"],
            settlement_service_scheme=settlement_service["scheme"],
            settlement_service_domain=settlement_service["host"],
            settlement_service_port=settlement_service["port"],
            authentication_token=settlement_service.get("auth_token", None),
        )
        if contract_data2["address"] != contract_data["address"]:
            raise StablehedgeException("Contract address from settlement service mismatched")

        contract_data = contract_data2

        funding_amounts = ScriptFunctions.calculateTotalFundingSatoshis(dict(
            contractData=contract_data,
            anyhedgeVersion=contract_data["version"],
        ))
        data_str = GP_LP.json_parser.dumps(funding_amounts, indent=2)
        LOGGER.debug(f"FUNDING AMOUNTS | {treasury_contract_address} | {data_str}")

        funding_sats = funding_amounts["shortFundingUtxoSats"]
        funding_utxo_build_result = build_or_find_funding_utxo(treasury_contract_address, satoshis=funding_sats)
        funding_utxo = funding_utxo_build_result["utxo"]
        funding_utxo_tx = funding_utxo_build_result["transaction"]
        input_tx_hashes = funding_utxo_build_result["input_tx_hashes"]

        result = ScriptFunctions.spendToAnyhedgeContract(dict(
            contractOpts=treasury_contract.contract_opts,
            contractData=contract_data,
            inputs=[
                funding_utxo,
                dict(
                    txid="0" * 64, vout=0, satoshis=funding_amounts["longFundingSats"] + 141 + 35,
                    lockingBytecode="0" * 50, # p2pkh locking bytecode length = 25 bytes
                    unlockingBytecode="0" * (98 * 2), # 65 byte schnorr signature + 33 byte pubkey
                ),
            ],
            outputs=[
                dict(to=contract_data["address"], amount=funding_amounts["totalFundingSats"]),
            ]
        ))

        data_str = GP_LP.json_parser.dumps(result, indent=2)
        LOGGER.debug(f"SPEND TO ANYHEDGE | {treasury_contract_address} | {data_str}")

        if not result.get("success"):
            raise StablehedgeException(result.get("error", "Failed to build funding tx"))

        funding_transaction = result["tx_hex"]
        unlocking_bytecode = extract_unlocking_script(funding_transaction, index=0)
        funding_proposal=dict(
            txHash=funding_utxo["txid"],
            txIndex=funding_utxo["vout"],
            txValue=funding_utxo["satoshis"],
            unlockingScript=unlocking_bytecode,
            inputTxHashes=input_tx_hashes,
        )

        data_str = GP_LP.json_parser.dumps(funding_proposal, indent=2)
        LOGGER.debug(f"FUNDING PROPOSAL | {treasury_contract_address} | {data_str}")

        if funding_utxo_tx:
            LOGGER.debug(f"FUNDING UTXO TX | {treasury_contract_address} | {funding_utxo_tx}")
            success, error_or_txid = broadcast_transaction(funding_utxo_tx)
            if not success:
                raise StablehedgeException(
                    f"Invalid funding utxo tx: {error_or_txid}", code="invalid_transaction"
                )

        hedge_pos_obj = complete_short_proposal_funding(
            treasury_contract_address,
            contract_data,
            settlement_service,
            funding_proposal,
        )
        return dict(success=True, address=hedge_pos_obj.address)
    except (AnyhedgeException, StablehedgeException) as error:
        return dict(success=False, error=str(error), code=error.code)
    finally:
        REDIS_STORAGE.delete(REDIS_KEY)


@shared_task(queue=_QUEUE_TREASURY_CONTRACT)
def check_treasury_contracts_for_rebalance():
    results = []
    for treasury_contract in models.TreasuryContract.objects.filter():
        try:
            result = rebalance_funds(treasury_contract.address)
            results.append([treasury_contract.address, result])
        except Exception as exception:
            results.append([treasury_contract.address, str(exception)])

    return results

@shared_task(queue=_QUEUE_TREASURY_CONTRACT)
def rebalance_funds(treasury_contract_address:str):
    REDIS_KEY = f"treasury-contract-rebalance-task-{treasury_contract_address}"

    if REDIS_STORAGE.exists(REDIS_KEY):
        return dict(success=False, error="Task key in use")

    LOGGER.info(f"ATTEMPTING REBALANCING | treasury contract | {treasury_contract_address}")
    try:
        REDIS_STORAGE.set(REDIS_KEY, "1", ex=120)
        tvl_data = _get_tvl_sats(treasury_contract_address)

        LOGGER.info(f"TVL DATA | {tvl_data}")

        total_tvl = tvl_data["total"]
        redeemable = tvl_data["redeemable"]

        required_sats = (total_tvl / 2) - redeemable
        transferrable = tvl_data["satoshis"]

        if required_sats <= 0:
            return dict(success=True, message="No rebalance required")

        satoshis_to_transfer = None
        if transferrable > required_sats:
            satoshis_to_transfer = int(required_sats)

        result = transfer_treasury_funds_to_redemption_contract(
            treasury_contract_address, satoshis=satoshis_to_transfer
        )

        LOGGER.info(f"REBALANCE TX RESULT | {json.dumps(result, indent=2)}")

        if not result["success"]:
            return result

        tx_hexes = result.pop("transactions", [])
        results = []
        for tx_hex in tx_hexes:
            success, txid_or_error = broadcast_transaction(tx_hex)
            if success:
                results.append((txid_or_error, None))
            else:
                results.append((txid_or_error, tx_hex))

        result["transactions"] = results
        return result

    except (AnyhedgeException, StablehedgeException) as error:
        return dict(success=False, error=str(error), code=error.code)
    except Exception as exception:
        REDIS_STORAGE.delete(REDIS_KEY)
        raise exception
    finally:
        REDIS_STORAGE.delete(REDIS_KEY)
