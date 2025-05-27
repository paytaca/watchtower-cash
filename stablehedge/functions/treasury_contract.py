import logging
from django.conf import settings
from django.db.models import Sum

from stablehedge.apps import LOGGER
from stablehedge import models
from stablehedge.js.runner import ScriptFunctions
from stablehedge.exceptions import StablehedgeException
from stablehedge.utils.wallet import to_cash_address, wif_to_cash_address, is_valid_wif, wif_to_pubkey
from stablehedge.utils.blockchain import broadcast_transaction, get_tx_hash
from stablehedge.utils.transaction import tx_model_to_cashscript
from stablehedge.utils.encryption import encrypt_str, decrypt_wif_safe


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
        raise StablehedgeException("Invalid signature/s", code="invalid_signature")

    sig_index = int(sig_index)
    if sig_index < 1 or sig_index > 3:
        raise StablehedgeException("Invalid index for signature", code="invalid_sig_index")
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
    fee_sats_per_input = 700

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


def get_funding_wif_address(treasury_contract_address:str, token=False):
    funding_wif = get_funding_wif(treasury_contract_address)
    if not funding_wif:
        return

    testnet = treasury_contract_address.startswith("bchtest:")
    return wif_to_cash_address(funding_wif, testnet=testnet, token=token)

def set_funding_wif(treasury_contract_address:str, wif:str):
    treasury_contract = models.TreasuryContract.objects.get(address=treasury_contract_address)
    if not is_valid_wif(wif):
        raise Exception("Invalid WIF")

    cleaned_wif = wif
    if wif.startswith("bch-wif:"):
        cleaned_wif = wif
    else:
        cleaned_wif = encrypt_str(wif)

    # check if it convertible to address
    wif_to_cash_address(wif.replace("bch-wif:", ""))

    treasury_contract.encrypted_funding_wif = cleaned_wif
    treasury_contract.save()
    return treasury_contract

def get_funding_wif(treasury_contract_address:str):
    encrypted_funding_wif = models.TreasuryContract.objects \
        .filter(address=treasury_contract_address) \
        .values_list("encrypted_funding_wif", flat=True) \
        .first()
    
    if not encrypted_funding_wif: return 

    # in case the saved data is not encrypted
    return decrypt_wif_safe(encrypted_funding_wif)


def sweep_funding_wif(treasury_contract_address:str):
    LOGGER.info(f"SWEEP FUNDING WIF | {treasury_contract_address}")
    funding_wif = get_funding_wif(treasury_contract_address)
    funding_wif_address = get_funding_wif_address(treasury_contract_address)

    utxos = main_models.Transaction.objects \
        .filter(spent=False, address__address=funding_wif_address)

    cashscript_utxos = []
    for utxo in utxos:
        cashscript_utxo = tx_model_to_cashscript(utxo)
        cashscript_utxo["wif"] = funding_wif
        cashscript_utxos.append(cashscript_utxo)

    if not len(cashscript_utxos):
        raise StablehedgeException("No UTXOs found in funding wif")

    tx_result = ScriptFunctions.sweepUtxos(dict(
        recipientAddress=treasury_contract_address,
        locktime=0,
        utxos=cashscript_utxos,
    ))

    if not tx_result["success"]:
        raise StablehedgeException(tx_result["error"])

    transaction = tx_result["transaction"]
    success, error_or_txid = broadcast_transaction(transaction)

    LOGGER.info(f"SWEEP FUNDING WIF | {treasury_contract_address} | {error_or_txid}")

    if not success:
        raise StablehedgeException(error_or_txid)

    return error_or_txid


def get_treasury_contract_wifs(treasury_contract_address:str):
    """
        Returns array of length 5, each index (0-4) matches pubkey 1 to 5
    """
    treasury_contract_keys = models.TreasuryContractKey.objects.filter(
        treasury_contract__address=treasury_contract_address,
    ).first()

    if not treasury_contract_keys:
        return

    wifs = [
        treasury_contract_keys.pubkey1_wif,
        treasury_contract_keys.pubkey2_wif,
        treasury_contract_keys.pubkey3_wif,
        treasury_contract_keys.pubkey4_wif,
        treasury_contract_keys.pubkey5_wif,
    ]
    for index, wif in enumerate(wifs):
        if not wif:
            continue
        wifs[index] = decrypt_wif_safe(wif)

    return wifs


def get_wif_for_short_proposal(treasury_contract:models.TreasuryContract):
    wifs = get_treasury_contract_wifs(treasury_contract.address)
    pubkeys = [
        treasury_contract.pubkey1,
        treasury_contract.pubkey2,
        treasury_contract.pubkey3,
        treasury_contract.pubkey4,
        treasury_contract.pubkey5,
    ]

    # first wif must be from pubkey1 since it used for short proposal
    # other wif is used for multisig
    wif1 = wifs[0]
    other_wifs = [_wif for _wif in wifs[1:] if _wif]

    return (wif1, *other_wifs[:2])

def get_funding_utxo_for_consolidation(treasury_contract_address:str, wif:str, utxos_count:int):
    if not wif:
        wif = get_funding_wif(treasury_contract_address)

    if not wif:
        raise StablehedgeException("Funding WIF not set", code="funding_wif_not_set")
    
    if not is_valid_wif(wif):
        raise StablehedgeException("Invalid funding WIF", code="invalid_funding_wif")

    address = wif_to_cash_address(wif, testnet=settings.BCH_NETWORK == "chipnet")
    return wif, main_models.Transaction.objects.filter(
        address__address=address,
        token__name="bch",
        spent=False,
        value__gte=1000 + utxos_count * 900,
    ).first()


def consolidate_treasury_contract(treasury_contract_address:str, satoshis:int=None, funding_wif:str=None):
    """
        Consolidate treasury contract utxos to a single tx
    """
    treasury_contract = models.TreasuryContract.objects.filter(address=treasury_contract_address).first()
    if not treasury_contract:
        raise StablehedgeException("Treasury contract not found", code="contract_not_found")

    # get utxos
    utxos = get_bch_utxos(treasury_contract_address, satoshis=satoshis)
    if not len(utxos):
        raise StablehedgeException("No UTXOs found", code="no_utxos")

    cashscript_utxos = [tx_model_to_cashscript(utxo) for utxo in utxos]

    fee_funder_wif, funding_utxo = get_funding_utxo_for_consolidation(
        treasury_contract_address, funding_wif, len(cashscript_utxos),
    )
    if not funding_utxo:
        raise StablehedgeException("Funding UTXO not found", code="funding_utxo_not_found")

    funding_utxo_data = tx_model_to_cashscript(funding_utxo)
    funding_utxo_data["wif"] = fee_funder_wif

    # create transaction
    result = ScriptFunctions.consolidateTreasuryContract(dict(
        contractOpts=treasury_contract.contract_opts,
        locktime=0,
        feeFunderUtxo=funding_utxo_data,
        inputs=cashscript_utxos,
        satoshis=satoshis,
    ))

    if "success" not in result or not result["success"]:
        raise StablehedgeException(result.get("error", "Unknown error"))

    return result["tx_hex"]


def build_or_find_funding_utxo(treasury_contract_address:str, satoshis:int=0):
    """
        Build or find funding utxo for treasury contract
    """
    funding_utxo = find_single_bch_utxo(treasury_contract_address, satoshis=satoshis)

    if funding_utxo:
        utxo_data = tx_model_to_cashscript(funding_utxo)
    else:
        transaction = consolidate_treasury_contract(treasury_contract_address, satoshis=satoshis)
        txid = get_tx_hash(transaction)
        utxo_data = dict(txid=txid, vout=0, satoshis=satoshis)

    return dict(
        utxo=utxo_data,
        transaction=transaction,
    )
