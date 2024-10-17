from django.db.models import signals
from django.dispatch import receiver

from rampp2p.slackbot.send import *
from rampp2p import models

import logging
logger = logging.getLogger(__name__)

@receiver(signals.post_save, sender=models.Status)
def on_order_update(sender, instance:models.Status, created:bool, raw:bool, using:str, update_fields:set, **kwargs):
    if created:
        OrderSummaryMessage.send_safe(instance.order.id)
        OrderStatusUpdateMessage.send_safe(instance.order.id)

    if (instance.status == models.StatusType.APPEALED or
        instance.status == models.StatusType.REFUND_PENDING or
        instance.status == models.StatusType.RELEASE_PENDING or
        instance.status == models.StatusType.REFUNDED or
        instance.status == models.StatusType.RELEASED):
        appeal = models.Appeal.objects.filter(order__id=instance.order.id).first()
        if appeal:
            AppealStatusUpdateMessage.send_safe(appeal.id, status=instance)

@receiver(signals.post_save, sender=models.Appeal)
def on_appeal_update(sender, instance:models.Appeal, created:bool, raw:bool, using:str, update_fields:set, **kwargs):
    AppealSummaryMessage.send_safe(instance.id)
