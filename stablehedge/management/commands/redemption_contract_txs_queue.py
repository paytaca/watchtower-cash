import time
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone

from stablehedge import models
from stablehedge.functions.transaction import (
    RedemptionContractTransactionException,
    broadcast_transaction,
    create_inject_liquidity_tx,
    create_deposit_tx,
    create_redeem_tx,
)

LOGGER = logging.getLogger("django")


class Command(BaseCommand):
    help = "Watches & executes transactions of redemption contract"

    def handle(self, *args, **options):
        LOG_RUNNING_INTERVAL = 30
        LOGGER.info("Running redemption contract transactions queue")
        last_log = 0
        while True:
            if last_log + LOG_RUNNING_INTERVAL > time.time():
                LOGGER.info("redemption contract transactions queue running")
                last_log = time.time()

            run_pending_transactions()
            time.sleep(1)


def run_pending_transactions():
    pending_txs_qs = models.RedemptionContractTransaction.objects \
        .filter(status=models.RedemptionContractTransaction.Status.PENDING)

    first_pending_tx_per_contract = pending_txs_qs \
        .order_by("redemption_contract", "created_at") \
        .distinct("redemption_contract")

    for pending_tx in first_pending_tx_per_contract:
        LOGGER.info(f"RedemptionContractTransaction#{pending_tx.id} | {pending_tx.transaction_type} |  {pending_tx.wallet_hash} | {pending_tx.redemption_contract.address} | {pending_tx.utxo}")
        resolve_transaction(pending_tx)
        LOGGER.info(f"RedemptionContractTransaction#{pending_tx.id} | {pending_tx.status} | {pending_tx.txid} | {pending_tx.result_message}")


def resolve_transaction(obj: models.RedemptionContractTransaction):
    if obj.status != models.RedemptionContractTransaction.Status.PENDING:
        return

    try:
        if obj.transaction_type == models.RedemptionContractTransaction.Type.INJECT:
            result = create_inject_liquidity_tx(obj)
        elif obj.transaction_type == models.RedemptionContractTransaction.Type.DEPOSIT:
            result = create_deposit_tx(obj)
        elif obj.transaction_type == models.RedemptionContractTransaction.Type.REDEEM:
            result = create_redeem_tx(obj)
        else:
            raise RedemptionContractTransactionException(f"Unknown transaction type '{obj.transaction_type}'")

        if not result["success"]:
            raise RedemptionContractTransactionException(result["error"])

        success, txid_or_error = broadcast_transaction(result["tx_hex"])
        if not success:
            raise RedemptionContractTransactionException(txid_or_error)
        obj.status = models.RedemptionContractTransaction.Status.SUCCESS
        obj.txid = txid_or_error
        obj.resolved_at = timezone.now()
        obj.save()
    except RedemptionContractTransactionException as error:
        obj.status = models.RedemptionContractTransaction.Status.FAILED
        obj.result_message = str(error)
        obj.resolved_at = timezone.now()
        obj.save()
    except Exception as exception:
        LOGGER.exception(exception)
