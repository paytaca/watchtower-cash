from stablehedge import models
from stablehedge.js.runner import ScriptFunctions
from stablehedge.exceptions import StablehedgeException
from stablehedge.utils.transaction import (
    tx_model_to_cashscript,
    utxo_data_to_cashscript,
)

from .auth_key import get_signed_auth_key_utxo
from .redemption_contract import find_fiat_token_utxos

def transfer_treasury_funds_to_redemption_contract(
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

    reserve_utxo = find_fiat_token_utxos(redemption_contract.address).first()

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
    return result
