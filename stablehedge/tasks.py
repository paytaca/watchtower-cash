from celery import shared_task
from django.conf import settings

from stablehedge import models
from stablehedge.apps import LOGGER
from stablehedge.js.runner import ScriptFunctions
from stablehedge.functions.anyhedge import (
    AnyhedgeException,
    StablehedgeException,
    get_short_contract_proposal,
    create_short_proposal,
    update_short_proposal_access_keys,
    update_short_proposal_funding_utxo_tx_sig,
    complete_short_proposal,
)
from stablehedge.functions.treasury_contract import (
    get_spendable_sats,
    get_wif_for_short_proposal
)
from stablehedge.utils.wallet import wif_to_pubkey

from anyhedge.utils.liquidity_provider import GeneralProtocolsLP

REDIS_STORAGE = settings.REDISKV
GP_LP = GeneralProtocolsLP()

_TASK_TIME_LIMIT = 300 # 5 minutes
_QUEUE_TREASURY_CONTRACT = "stablhedge__treasury_contract"


def check_and_short_funds(
    treasury_contract_address:str,
    min_sats:int=10 ** 8,
    background_task:bool=False,
):
    balance_data = get_spendable_sats(treasury_contract_address)
    spendable = balance_data["spendable"]
    if not spendable or spendable < min_sats:
        return dict(success=True, message="Balance not met")

    if background_task:
        task = short_treasury_contract_funds.delay(treasury_contract_address)
        result = dict(success=True, task_id=task.id)
    else:
        result = short_treasury_contract_funds(treasury_contract_address)

    return result
    

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


        contract_address = short_proposal["contract_data"]["address"]

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
