from celery import shared_task

from rampp2p.models import Status, Order, StatusType
from rampp2p.serializers import StatusSerializer
from django.db.models import OuterRef, Subquery
from django.utils import timezone
from rampp2p.validators import validate_status_inst_count, validate_status_progression

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
            status = StatusSerializer(data={
                'status': StatusType.CANCELED,
                'order': order.id
            })
            try:
                validate_status_inst_count(status, order.id)
                validate_status_progression(status, order.id)
                if status.is_valid():
                    status.save()
            except Exception as err:
                logger.warn(f'error: {err}')
            
            order.expires_at = None
            order.save()