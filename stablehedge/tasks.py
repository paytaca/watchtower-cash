from celery import shared_task

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
from stablehedge.functions.treasury_contract import get_wif_for_short_proposal
from stablehedge.utils.wallet import wif_to_pubkey

from anyhedge.utils.liquidity_provider import GeneralProtocolsLP

GP_LP = GeneralProtocolsLP()

_TASK_TIME_LIMIT = 300 # 5 minutes
_QUEUE_TREASURY_CONTRACT = "stablhedge__treasury_contract"

@shared_task(queue=_QUEUE_TREASURY_CONTRACT, time_limit=_TASK_TIME_LIMIT)
def short_treasury_contract_funds(treasury_contract_address:str):
    LOGGER.info(f"SHORT TREAURY CONTRACT | {treasury_contract_address}")
    try:
        treasury_contract = models.TreasuryContract.objects.filter(address=treasury_contract_address).first()
        if not treasury_contract:
            return dict(success=False, error="Treasury contract not found")

        # wif used for placing short positions
        # must the wif of treasury contract's pubkey1
        wif = get_wif_for_short_proposal(treasury_contract_address)

        if not wif:
            return dict(success=False, error="WIF for pubkey1 not found")

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

        signatures = ScriptFunctions.signMutliSigTx(dict(
            contractOpts=treasury_contract.contract_opts,
            wif=wif,
            locktime=0,
            inputs=funding_utxo_tx["inputs"],
            outputs=funding_utxo_tx["outputs"],
        ))
        data_str = GP_LP.json_parser.dumps(access_key_sign_result, indent=2)
        LOGGER.debug(f"SHORT PROPOSAL | FUNDING UTXO SIG | {treasury_contract_address} | {data_str}")
        update_short_proposal_funding_utxo_tx_sig(treasury_contract_address, signatures, 1)
        update_short_proposal_funding_utxo_tx_sig(treasury_contract_address, signatures, 2)
        update_short_proposal_funding_utxo_tx_sig(treasury_contract_address, signatures, 3)

        hedge_pos_obj = complete_short_proposal(treasury_contract_address)
        return dict(success=True, address=hedge_pos_obj.address)
    except (AnyhedgeException, StablehedgeException) as error:
        return dict(success=False, error=str(error), code=error.code)
