from stablehedge import models
from stablehedge.utils.transaction import (
    validate_utxo_data,
    tx_model_to_cashscript,
    utxo_data_to_cashscript,
    InvalidUtxoException,
)
from stablehedge.utils.address import (
    locking_bytecode_to_address,
    to_cash_address,
)
from stablehedge.js.runner import ScriptFunctions

from .redemption_contract import find_fiat_token_utxos

from main.tasks import NODE
from main.models import TransactionBroadcast
from main.tasks import broadcast_transaction as broadcast_transaction_task
from main.utils.broadcast import send_post_broadcast_notifications

class RedemptionContractTransactionException(Exception):
    def __init__(self, *args, code=None, **kwargs):
        self.code = code
        super().__init__(*args, **kwargs)

def test_transaction_accept(transaction):
    test_accept = NODE.BCH.test_mempool_accept(transaction)
    if not test_accept["allowed"]:
        return False, test_accept["reject-reason"]

    return True, test_accept["txid"]


def broadcast_transaction(transaction):
    valid_tx, error_or_txid = test_transaction_accept(transaction)
    if not valid_tx:
        return False, error_or_txid

    txid = error_or_txid

    txn_broadcast = TransactionBroadcast.objects.create(
        txid=txid,
        tx_hex=transaction
    )
    broadcast_transaction.delay(transaction, txid, txn_broadcast.id)
    send_post_broadcast_notifications(transaction)
    return True, txid


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
    ))

    if not result["success"]:
        error = result.get("error", "Unknown script error")
        raise RedemptionContractTransactionException(error)

    valid_tx, error_or_txid = test_transaction_accept(result["tx_hex"])
    if not valid_tx:
        result["success"] = False
        result["error"] = error_or_txid

    return result
