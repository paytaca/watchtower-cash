from django.db.models import signals
from django.dispatch import receiver

from rampp2p.slackbot.send import OrderStatusUpdateMessage, OrderSummaryMessage
from rampp2p import models

import logging
logger = logging.getLogger(__name__)

@receiver(signals.post_save, sender=models.Status)
def on_status_update(sender, instance:models.Status, created:bool, raw:bool, using:str, update_fields:set, **kwargs):
    logger.warning(f'on_status_update: {sender} | created: {created}')
    if created:
        # OrderSummaryMessage.send_safe(instance.order.id)
        OrderStatusUpdateMessage.send_safe(instance.order.id)

@receiver(signals.post_save, sender=models.Order)
def on_order_created(sender, instance:models.Order, created:bool, raw:bool, using:str, update_fields:set, **kwargs):
    logger.warning(f'on_order_created: {sender} | created: {created}')
    if not created:
        OrderSummaryMessage.send_safe(instance.id)
