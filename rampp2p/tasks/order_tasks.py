from celery import shared_task

from rampp2p.models import Status, Order, StatusType
from rampp2p.serializers import StatusSerializer
from django.db.models import OuterRef, Subquery
from django.utils import timezone

import logging
logger = logging.getLogger(__name__)

@shared_task(queue='rampp2p__cancel_expired_orders')
def cancel_expired_orders():
    # find expired orders with status SUBMITTED and expires_at 
    last_status = Status.objects.filter(
        order=OuterRef('pk'),
        status__in=[StatusType.SUBMITTED]
    ).order_by('-created_at').values('order')[:1]
    submitted_orders = Order.objects.filter(pk__in=Subquery(last_status))
    submitted_orders = submitted_orders.filter(expires_at__isnull=False)
    # cancel expired orders
    for order in submitted_orders:
        if order.expires_at < timezone.now():
            serialized_status = StatusSerializer(data={
                'status': StatusType.CANCELED,
                'order': order.id
            })
            if serialized_status.is_valid():
                serialized_status.save()