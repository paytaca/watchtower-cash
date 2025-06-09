from stablehedge import models
from stablehedge.js.runner import ScriptFunctions
from stablehedge.exceptions import StablehedgeException
from stablehedge.utils.blockchain import get_tx_hash
from stablehedge.utils.transaction import (
    tx_model_to_cashscript,
    utxo_data_to_cashscript,
    decode_raw_tx,
)

from .auth_key import get_signed_auth_key_utxo
from .redemption_contract import find_fiat_token_utxos, consolidate_redemption_contract
from .treasury_contract import get_bch_utxos, consolidate_treasury_contract


def transfer_treasury_funds_to_redemption_contract(
    treasury_contract_address,
    satoshis:int=None,
    locktime:int=0,
):
    try:
        return transfer_treasury_funds_to_redemption_contract_with_nft(
            treasury_contract_address,
            satoshis=satoshis,
            locktime=locktime,
        )
    except StablehedgeException as e:
        if e.code not in ["mismatch-auth-token", "no-auth-key-utxo"]:
            raise e

    return unmonitored_rebalance(treasury_contract_address, satoshis=satoshis, locktime=locktime)


def transfer_treasury_funds_to_redemption_contract_with_nft(
    treasury_contract_address,
    satoshis:int=None,
    locktime:int=0,
):
    """
        Move satoshis from treasury contract to redemption contract's reserve UTXO
    """
    treasury_contract = models.TreasuryContract.objects.get(address=treasury_contract_address)
    redemption_contract = treasury_contract.redemption_contract
    if not redemption_contract:
        raise StablehedgeException("No redemption contract", code="no-redemption-contract")

    if redemption_contract.auth_token_id != treasury_contract.auth_token_id:
        raise StablehedgeException("Mismatch in auth token", code="mismatch-auth-token")

    reserve_utxo = find_fiat_token_utxos(redemption_contract).first()

    treasury_contract_utxos = get_bch_utxos(treasury_contract_address, satoshis=satoshis)

    signed_auth_key = get_signed_auth_key_utxo(
        redemption_contract.auth_token_id,
        locktime=locktime,
    )

    opts = dict(
        treasuryContractOpts=treasury_contract.contract_opts,
        redemptionContractOpts=redemption_contract.contract_opts,
        satoshis=satoshis,
        treasuryContractUtxos=[tx_model_to_cashscript(utxo) for utxo in treasury_contract_utxos],
        reserveUtxo=tx_model_to_cashscript(reserve_utxo),
        authKeyUtxo=signed_auth_key,
        locktime=locktime,
    )

    result = ScriptFunctions.transferTreasuryFundsToRedemptionContract(opts)
    if not result["success"]:
        return result

    return dict(
        success=True,
        transactions=[result["tx_hex"]],
    )


def unmonitored_rebalance(
    treasury_contract_address:str,
    satoshis:int=None,
    locktime:int=0,
):
    treasury_contract = models.TreasuryContract.objects.get(address=treasury_contract_address)
    redemption_contract = treasury_contract.redemption_contract
    if not redemption_contract:
        raise StablehedgeException("No redemption contract", code="no-redemption-contract")

    if redemption_contract.version == models.RedemptionContract.Version.V1:
        raise StablehedgeException("Redemption contract is V1", code="invalid-redemption-contract-version")

    tc_consolidate_tx = consolidate_treasury_contract(
        treasury_contract.address,
        satoshis=satoshis,
        to_redemption_contract=True,
        locktime=locktime,
    )

    if not satoshis:
        tc_transaction_data = decode_raw_tx(tc_consolidate_tx)
        transferred_sats = tc_transaction_data["vout"][2]["value"] * 10 ** 8
    else:
        transferred_sats = satoshis

    manual_utxo = dict(
        txid=get_tx_hash(tc_consolidate_tx),
        vout=2,
        satoshis=transferred_sats,
    )

    rc_consolidate_tx = consolidate_redemption_contract(
        redemption_contract.address,
        with_reserve_utxo=True,
        manual_utxos=[manual_utxo],
        append_manual_utxos=True,
    )

    return dict(success=True, transactions=[tc_consolidate_tx, rc_consolidate_tx])
