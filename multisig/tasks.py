import logging
from django.db import transaction
from celery import shared_task
from multisig.js_client import get_unsigned_transaction_hash
from multisig.models import Proposal

LOGGER = logging.getLogger(__name__)


@shared_task(rate_limit="2/s", queue="post_save_record")
def update_proposal_status_on_broadcast(transaction_broadcast_id, txid, tx_hex):
    try:
        response = get_unsigned_transaction_hash(tx_hex)
        if response.status_code != 200:
            LOGGER.error(
                f"get_unsigned_transaction_hash failed with status {response.status_code}"
            )
            return
        response_json = response.json()
        unsigned_transaction_hash = response_json.get("unsigned_transaction_hash")
    except Exception as e:
        LOGGER.exception(f"Error getting unsigned transaction hash: {e}")
        return

    if not unsigned_transaction_hash:
        LOGGER.warning(f"No unsigned_transaction_hash found for tx_hex")
        return

    proposal = Proposal.objects.filter(
        unsigned_transaction_hash=unsigned_transaction_hash
    ).first()

    if proposal:
        with transaction.atomic():
            proposal.txid = txid
            proposal.status = Proposal.Status.BROADCAST_INITIATED
            proposal.on_premise_transaction_broadcast_id = transaction_broadcast_id
            proposal.save(
                update_fields=["txid", "status", "on_premise_transaction_broadcast"]
            )

            if proposal.inputs.exists():
                for input in proposal.inputs.all():
                    input.spending_txid = txid
                    input.save()
                LOGGER.info(f"Updated proposal {proposal.id} with txid {txid}")
    else:
        LOGGER.warning(
            f"No proposal found for unsigned_transaction_hash {unsigned_transaction_hash}"
        )
