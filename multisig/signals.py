import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from main.models import (
    TransactionBroadcast,
)
from multisig.tasks import update_proposal_status_on_broadcast

LOGGER = logging.getLogger(__name__)

@receiver(post_save, sender=TransactionBroadcast)
def transaction_broadcast_post_save(sender, instance=None, created=False, **kwargs):
    LOGGER.info(f"created {instance}")
    if created and instance.tx_hex:
        update_proposal_status_on_broadcast.delay(instance.id, instance.txid, instance.tx_hex)
        