
import logging
from django.db import transaction, IntegrityError
from celery import shared_task
from multisig.js_client import get_unsigned_transaction_hash
from multisig.models import Proposal

LOGGER = logging.getLogger(__name__)

@shared_task(rate_limit='20/s', queue='post_save_record')
def update_proposal_status_on_broadcast(transaction_broadcast_id, txid, tx_hex):
    
    LOGGER.info(f"broadcasted_tx_hex {tx_hex}")
    unsigned_transaction_hash = None
    response = get_unsigned_transaction_hash(tx_hex)
    if response.status_code == 200:
        response_json = response.json()
        LOGGER.info(f"response_json {response_json}")
        unsigned_transaction_hash = response_json.get('unsigned_transaction_hash')

    if unsigned_transaction_hash:
        LOGGER.info(f"unsigned_transaction_hash {unsigned_transaction_hash}")
        proposal = Proposal.objects.filter(
            unsigned_transaction_hash=unsigned_transaction_hash
        ).first()

        with transaction.atomic():
            if proposal:
                proposal.txid = txid
                proposal.status = Proposal.Status.BROADCAST_INITIATED
                proposal.on_premise_transaction_broadcast_id = transaction_broadcast_id
                proposal.save(update_fields=["txid", "status", "on_premise_transaction_broadcast"])
            if proposal.inputs:
                for input in proposal.inputs.all():
                    input.spending_txid = txid
                    input.save()
                    LOGGER.info(f"Proposal Found {proposal}")

