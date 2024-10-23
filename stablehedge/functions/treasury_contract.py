import logging
from django.conf import settings
from django.db.models import Sum

from stablehedge import models
from stablehedge.js.runner import ScriptFunctions
from stablehedge.utils.address import to_cash_address

from anyhedge.utils.contract import AnyhedgeException

from main import models as main_models

def save_signature_to_tx(
    treasury_contract:models.TreasuryContract,
    tx_data:dict,
    sig:list,
    sig_index:int
):
    verify_result = ScriptFunctions.verifyTreasuryContractMultisigTx(dict(
        contractOpts=treasury_contract.contract_opts,
        sig=sig,
        locktime=tx_data.get("locktime", 0),
        inputs=tx_data["inputs"],
        outputs=tx_data["outputs"],
    ))

    if not verify_result.get("valid"):
        logging.exception(f"verify_result | {treasury_contract_address.address} | {verify_result}")
        raise AnyhedgeException("Invalid signature/s", code="invalid_signature")

    sig_index = int(sig_index)
    if sig_index < 1 or sig_index > 3:
        raise AnyhedgeException("Invalid index for signature", code="invalid_sig_index")
    tx_data[f"sig{sig_index}"] = sig

    return tx_data


def get_spendable_sats(treasury_contract_address:str):
    utxos = get_bch_utxos(treasury_contract_address)

    if isinstance(utxos, list):
        total_sats = 0
        for utxo in utxos:
            total_sats += utxo.value

        utxo_count = len(utxos)
    else:
        total_sats = utxos.aggregate(total_sats = Sum("value"))["total_sats"] or 0
        utxo_count = utxos.count()
 
    # estimate of sats used as fee when using the utxo
    # need to improve
    fee_sats_per_input = 500
    spendable_sats = total_sats - (fee_sats_per_input * utxo_count)

    return dict(total=total_sats, spendable=spendable_sats, utxo_count=utxo_count)


def find_single_bch_utxo(treasury_contract_address:str, satoshis:int):
    address = to_cash_address(treasury_contract_address, testnet=settings.BCH_NETWORK == "chipnet")
    return main_models.Transaction.objects.filter(
        address__address=address,
        token__name="bch",
        spent=False,
        value=satoshis,
    ).first()


def get_bch_utxos(treasury_contract_address:str, satoshis:int=None):
    address = to_cash_address(treasury_contract_address, testnet=settings.BCH_NETWORK == "chipnet")
    utxos = main_models.Transaction.objects.filter(
        address__address=address,
        token__name="bch",
        spent=False,
    )
    if satoshis is None:
        return utxos

    P2PKH_OUTPUT_FEE = 44
    fee_sats_per_input = 500

    subtotal = 0
    sendable = 0 - (P2PKH_OUTPUT_FEE * 2) # 2 outputs for send and change
    _utxos = []
    for utxo in utxos:
        subtotal += utxo.value
        sendable += utxo.value - fee_sats_per_input
        _utxos.append(utxo)

        if sendable >= satoshis:
            break


    return _utxos
