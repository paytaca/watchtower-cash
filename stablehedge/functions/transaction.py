import re
import decimal
import json

from django.db.models import Q

from stablehedge import models
from stablehedge.apps import LOGGER
from stablehedge.utils.blockchain import (
    get_locktime,
    test_transaction_accept,
    resolve_spending_txid,
)
from stablehedge.utils.transaction import (
    validate_utxo_data,
    tx_model_to_cashscript,
    utxo_data_to_cashscript,
    InvalidUtxoException,
)
from stablehedge.utils.wallet import (
    locking_bytecode_to_address,
    to_cash_address,
)
from stablehedge.js.runner import ScriptFunctions

from .redemption_contract import find_fiat_token_utxos

from main import models as main_models
from main.tasks import NODE, process_mempool_transaction_fast
from main.utils.broadcast import send_post_broadcast_notifications

class RedemptionContractTransactionException(Exception):
    def __init__(self, *args, code=None, **kwargs):
        self.code = code
        super().__init__(*args, **kwargs)

def create_inject_liquidity_tx(redemption_contract_tx:models.RedemptionContractTransaction):
    tx_type = redemption_contract_tx.transaction_type

    if tx_type != models.RedemptionContractTransaction.Type.INJECT:
        raise RedemptionContractTransactionException("Invalid transaction type", code="invalid_tx_type")

    deposit_utxo = redemption_contract_tx.utxo
    redemption_contract = redemption_contract_tx.redemption_contract
    price_message = redemption_contract_tx.price_oracle_message

    try:
        validate_utxo_data(deposit_utxo, require_unlock=True, raise_error=True)
    except InvalidUtxoException as exception:
        raise RedemptionContractTransactionException(str(exception))
    reserve_utxo = find_fiat_token_utxos(redemption_contract).first()
    if not reserve_utxo:
        raise RedemptionContractTransactionException("No usable reserve utxo found", code="missing_reserve_utxo")

    locking_bytecode = deposit_utxo["locking_bytecode"]
    try:
        recipient_address = locking_bytecode_to_address(locking_bytecode)
        recipient_address = to_cash_address(recipient_address, testnet=redemption_contract.network)
    except ValueError:
        raise RedemptionContractTransactionException(
            f"Invalid locking bytecode {locking_bytecode}",
            code="invalid_locking_bytecode",
        )

    result = ScriptFunctions.deposit(dict(
        contractOpts=redemption_contract.contract_opts,
        reserveUtxo=tx_model_to_cashscript(reserve_utxo),
        depositUtxo=utxo_data_to_cashscript(deposit_utxo),
        recipientAddress=recipient_address,
        priceMessage=price_message.message,
        priceMessageSig=price_message.signature,
        locktime=get_locktime(),
    ))

    if not result["success"]:
        error = result.get("error", "Unknown script error")
        raise RedemptionContractTransactionException(error)

    valid_tx, error_or_txid = test_transaction_accept(result["tx_hex"])
    if not valid_tx:
        result["success"] = False
        result["error"] = error_or_txid

    return result


def create_deposit_tx(redemption_contract_tx:models.RedemptionContractTransaction):
    tx_type = redemption_contract_tx.transaction_type

    if tx_type != models.RedemptionContractTransaction.Type.DEPOSIT:
        raise RedemptionContractTransactionException("Invalid transaction type", code="invalid_tx_type")

    deposit_utxo = redemption_contract_tx.utxo
    redemption_contract = redemption_contract_tx.redemption_contract
    price_message = redemption_contract_tx.price_oracle_message

    try:
        validate_utxo_data(deposit_utxo, require_unlock=True, raise_error=True)
    except InvalidUtxoException as exception:
        raise RedemptionContractTransactionException(str(exception))
    reserve_utxo = find_fiat_token_utxos(redemption_contract).first()
    if not reserve_utxo:
        raise RedemptionContractTransactionException("No usable reserve utxo found", code="missing_reserve_utxo")

    locking_bytecode = deposit_utxo["locking_bytecode"]
    try:
        recipient_address = locking_bytecode_to_address(locking_bytecode)
        recipient_address = to_cash_address(recipient_address, testnet=redemption_contract.network)
    except ValueError:
        raise RedemptionContractTransactionException(
            f"Invalid locking bytecode {locking_bytecode}",
            code="invalid_locking_bytecode",
        )

    result = ScriptFunctions.deposit(dict(
        contractOpts=redemption_contract.contract_opts,
        reserveUtxo=tx_model_to_cashscript(reserve_utxo),
        depositUtxo=utxo_data_to_cashscript(deposit_utxo),
        recipientAddress=recipient_address,
        treasuryContractAddress=redemption_contract.treasury_contract_address,
        priceMessage=price_message.message,
        priceMessageSig=price_message.signature,
        fee=redemption_contract_tx.fee_sats,
        locktime=get_locktime(),
    ))

    if not result["success"]:
        error = result.get("error", "Unknown script error")
        raise RedemptionContractTransactionException(error)

    valid_tx, error_or_txid = test_transaction_accept(result["tx_hex"])
    if not valid_tx:
        result["success"] = False
        result["error"] = error_or_txid

    return result


def create_redeem_tx(redemption_contract_tx:models.RedemptionContractTransaction):
    tx_type = redemption_contract_tx.transaction_type

    if tx_type != models.RedemptionContractTransaction.Type.REDEEM:
        raise RedemptionContractTransactionException("Invalid transaction type", code="invalid_tx_type")

    redeem_utxo = redemption_contract_tx.utxo
    redemption_contract = redemption_contract_tx.redemption_contract
    price_message = redemption_contract_tx.price_oracle_message

    try:
        validate_utxo_data(redeem_utxo, require_cashtoken=True, require_unlock=True, raise_error=True)
    except InvalidUtxoException as exception:
        raise RedemptionContractTransactionException(str(exception))

    reserve_utxo = find_fiat_token_utxos(redemption_contract).first()
    if not reserve_utxo:
        raise RedemptionContractTransactionException("No usable reserve utxo found", code="missing_reserve_utxo")

    locking_bytecode = redeem_utxo["locking_bytecode"]
    try:
        recipient_address = locking_bytecode_to_address(locking_bytecode)
        recipient_address = to_cash_address(recipient_address, testnet=redemption_contract.network)
    except ValueError:
        raise RedemptionContractTransactionException(
            f"Invalid locking bytecode {locking_bytecode}",
            code="invalid_locking_bytecode",
        )

    result = ScriptFunctions.redeem(dict(
        contractOpts=redemption_contract.contract_opts,
        reserveUtxo=tx_model_to_cashscript(reserve_utxo),
        redeemUtxo=utxo_data_to_cashscript(redeem_utxo),
        recipientAddress=recipient_address,
        priceMessage=price_message.message,
        priceMessageSig=price_message.signature,
        fee=redemption_contract_tx.fee_sats,
        locktime=get_locktime(),
    ))

    if not result["success"]:
        error = result.get("error", "Unknown script error")
        raise RedemptionContractTransactionException(error)

    valid_tx, error_or_txid = test_transaction_accept(result["tx_hex"])
    if not valid_tx:
        result["success"] = False
        result["error"] = error_or_txid

    return result

def resolve_failed_redemption_tx(obj:models.RedemptionContractTransaction):
    if obj.status != models.RedemptionContractTransaction.Status.FAILED:
        return

    # since there 2 inputs only, if deposit/redeem utxo is unspent,
    # the missing input is the reserve utxo, which we can try to rerun
    if obj.result_message == "missing-inputs" and \
        obj.utxo and obj.utxo.get("txid") and \
        NODE.BCH.rpc_connection.gettxout(obj.utxo["txid"], obj.utxo["vout"]):

        if obj.retry_count < 3:
            obj.retry_count += 1
            obj.status = models.RedemptionContractTransaction.Status.PENDING
            obj.save()
            return "retry"
        else:
            return "max-retries-reached"

    if obj.result_message in ["18: txn-already-in-mempool", "18: txn-mempool-conflict", "missing-inputs"] or \
        re.match("(insufficient|not enough).*(BCH)?.*(balance|funds)", obj.result_message, re.IGNORECASE):
        result = check_existing_txid_for_redemption_contract_tx(obj)
        return result["message"]


def check_existing_txid_for_redemption_contract_tx(obj:models.RedemptionContractTransaction, force=False):
    LOGGER.debug(f"RedemptionContractTransaction#{obj.id} | CHECKING EXISTING TX")
    if obj.txid and not force:
        return dict(success=True, txid=obj.txid, message="resolved-txid")

    txid = obj.utxo["txid"]
    vout = obj.utxo["vout"]
    spending_txid = resolve_spending_txid(txid, vout)
    if not spending_txid:
        return dict(success=True, message="utxo-unspent-or-missing")

    data = check_transaction_for_redemption_contract_tx(spending_txid)
    LOGGER.debug(f"RedemptionContractTransaction#{obj.id} | SPENDING TX DATA | {data}")
    if not data:
        return dict(success=False, message="no-tx-data")

    if obj.redemption_contract.address != data["redemption_contract_address"]:
        return dict(success=False, message="contract-mismatch")
    
    if obj.transaction_type != data["tx_type"]:
        return dict(success=False, message="tx-type-mismatch")

    obj.txid = spending_txid
    obj.status = models.RedemptionContractTransaction.Status.SUCCESS
    obj.save()
    return dict(success=True, txid=obj.txid, message="resolved-existing-tx")


def check_transaction_for_redemption_contract_tx(txid:str):
    tx_data = NODE.BCH.get_transaction(txid)

    if not tx_data: return
    if len(tx_data["inputs"]) < 2 or len(tx_data["outputs"]) < 2: return

    input_0 = tx_data["inputs"][0]
    output_0 = tx_data["outputs"][0]

    input_1 = tx_data["inputs"][1]
    output_1 = tx_data["outputs"][1]

    try:
        if not input_0["address"] or input_0["address"] != output_0["address"]:
            return
        elif input_0["token_data"]["category"] != output_0["token_data"]["category"]:
            return

        reserve_sats_diff = output_0["value"] - input_0["value"]
        reserve_token_diff = decimal.Decimal(output_0["token_data"]["amount"]) - decimal.Decimal(input_0["token_data"]["amount"])

        input_sats = input_1["value"]
        input_tokens = decimal.Decimal(input_1["token_data"]["amount"]) if input_1.get("token_data") else None

        output_sats = output_1["value"]
        output_tokens = decimal.Decimal(output_1["token_data"]["amount"]) if output_1.get("token_data") else None
    except (KeyError, TypeError) as exception:
        LOGGER.exception(exception)
        return

    tx_type = None
    if reserve_token_diff > 0:
        tx_type = models.RedemptionContractTransaction.Type.REDEEM
    elif reserve_token_diff < 0:
        if input_sats - 2000 == reserve_sats_diff:
            tx_type = models.RedemptionContractTransaction.Type.INJECT
        else:
            tx_type = models.RedemptionContractTransaction.Type.DEPOSIT

    utxo=dict(
        txid=input_1["txid"],
        vout=input_1["spent_index"],
        satoshis=input_1["value"],
    )
    if input_1.get("token_data"):
        utxo["category"] = input_1["token_data"]["category"]
        utxo["amount"] = input_1["token_data"]["amount"]

    return dict(
        txid=txid,
        redemption_contract_address=input_0["address"],
        tx_type=tx_type,
        utxo=utxo,
    )

def update_redemption_contract_tx_trade_sizes():
    queryset = models.RedemptionContractTransaction.objects \
        .filter(status=models.RedemptionContractTransaction.Status.SUCCESS) \
        .filter(
            Q(trade_size_in_satoshis__isnull=True) | Q(trade_size_in_token_units__isnull=True)
        )

    for obj in queryset:
        update_redemption_contract_tx_trade_size(obj)

    return queryset.count()


def update_redemption_contract_tx_trade_size(
    redemption_contract_tx:models.RedemptionContractTransaction,
    save=True,
):
    price_value = decimal.Decimal(redemption_contract_tx.price_oracle_message.price_value)

    if redemption_contract_tx.transaction_type == models.RedemptionContractTransaction.Type.REDEEM:
        token_units = decimal.Decimal(redemption_contract_tx.utxo["amount"])
        bch = token_units / price_value
        satoshis = round(bch * decimal.Decimal(10 ** 8))
        # NOTE: fee_sats not included here, it's just deducted from the redeem satoshis;
        #       which is the actual trade size in sats.
        #       unlike deposit (below) where deposit sats is deducted by fee first before
        #       fetching the payout token amount
    else:
        fee_sats = redemption_contract_tx.fee_sats or 0
        satoshis = decimal.Decimal(redemption_contract_tx.utxo["satoshis"] - 2000 - fee_sats)
        bch = satoshis / 10 ** 8
        token_units = round(bch * price_value)

    redemption_contract_tx.trade_size_in_satoshis = satoshis
    redemption_contract_tx.trade_size_in_token_units = token_units
    LOGGER.info(f"{redemption_contract_tx} | satoshis={satoshis} | token_units={token_units}")

    if save:
        redemption_contract_tx.save()

    return redemption_contract_tx


def get_redemption_contract_tx_meta(redemption_contract_tx:models.RedemptionContractTransaction):
    if not redemption_contract_tx.txid:
        return dict(success=False, error="No txid")

    update_redemption_contract_tx_trade_size(redemption_contract_tx)

    redemption_contract_address = redemption_contract_tx.redemption_contract.address
    txid = redemption_contract_tx.txid
    tx_type = redemption_contract_tx.transaction_type
    price_value = redemption_contract_tx.price_oracle_message.price_value
    currency = redemption_contract_tx.redemption_contract.fiat_token.currency
    decimals = redemption_contract_tx.redemption_contract.fiat_token.decimals

    trade_size_amount = round(redemption_contract_tx.trade_size_in_token_units / 10 ** decimals, decimals)
    data = {
        "id": redemption_contract_tx.id,
        "redemption_contract": redemption_contract_address,
        "transaction_type": tx_type,
        "price": round(price_value / 10 ** decimals, decimals),
        "currency": currency,
        "satoshis": str(redemption_contract_tx.trade_size_in_satoshis),
        "amount": "{:.{}f}".format(trade_size_amount, decimals),
    }

    return dict(success=True, data=data, txid=txid)


def save_redemption_contract_tx_meta(redemption_contract_tx:models.RedemptionContractTransaction):
    result = get_redemption_contract_tx_meta(redemption_contract_tx)
    if not result["success"]:
        return result

    data = result["data"]
    txid = redemption_contract_tx.txid

    obj, created = main_models.TransactionMetaAttribute.objects.update_or_create(
        txid=txid,
        system_generated=True,
        key="stablehedge_transaction",
        defaults=dict(
            wallet_hash=redemption_contract_tx.wallet_hash or "",
            value=json.dumps(data),
        )
    )
    result["new"] = created
    
    # remove later on
    # from django.conf import settings
    # if settings.BCH_NETWORK == "chipnet":
    #     url = "https://chipnet.watchtower.cash/api/transactions/attributes/"
    # else:
    #     url = "https://watchtower.cash/api/transactions/attributes/"
    
    # _data = {
    #     "txid": txid,
    #     "wallet_hash": redemption_contract_tx.wallet_hash or "",
    #     "key": "stablehedge_transaction",
    #     "value": json.dumps(data),
    # }
    # import requests
    # requests.post(url, data=_data)

    return result
