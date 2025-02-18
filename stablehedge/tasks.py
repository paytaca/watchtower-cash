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
    update_short_proposal_access_keys,
    update_short_proposal_funding_utxo_tx_sig,
    complete_short_proposal,
    _get_tvl_sats,
)
from stablehedge.functions.treasury_contract import (
    get_spendable_sats,
    get_wif_for_short_proposal
)
from stablehedge.utils.blockchain import broadcast_transaction
from stablehedge.utils.wallet import wif_to_pubkey

from anyhedge.utils.liquidity_provider import GeneralProtocolsLP

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
    REDIS_KEY = f"treasury-contract-short-pos-task-{treasury_contract_address}"
    if REDIS_STORAGE.exists(REDIS_KEY):
        return dict(success=False, error="Task key in use")

    LOGGER.info(f"SHORT TREAURY CONTRACT | {treasury_contract_address}")
    try:
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
            satoshis_to_transfer = required_sats

        result = transfer_treasury_funds_to_redemption_contract(
            treasury_contract_address, satoshis=satoshis_to_transfer
        )

        LOGGER.info(f"REBALANCE TX RESULT | {json.dumps(result, indent=2)}")

        if not result["success"]:
            return result

        success, txid_or_error = broadcast_transaction(result["tx_hex"])
        if not success:
            return dict(success=False, error=txid_or_error, tx_hex=result["tx_hex"])

        result.pop("tx_hex", None)
        result["txid"] = txid_or_error
        return result

    except (AnyhedgeException, StablehedgeException) as error:
        return dict(success=False, error=str(error), code=error.code)
    except Exception as exception:
        REDIS_STORAGE.delete(REDIS_KEY)
        raise exception
    finally:
        REDIS_STORAGE.delete(REDIS_KEY)
