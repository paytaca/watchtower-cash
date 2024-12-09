from celery import shared_task

from rampp2p.models import Status, Order, StatusType
from rampp2p.serializers import StatusSerializer
from django.db.models import OuterRef, Subquery
from django.utils import timezone
from datetime import timedelta
from rampp2p.validators import validate_status_inst_count, validate_status_progression

import logging
logger = logging.getLogger(__name__)

@shared_task(queue='rampp2p__cancel_expired_orders')
def cancel_expired_orders():
    # find expired orders with status SUBMITTED
    latest_status_subquery = Status.objects.filter(
        order=OuterRef('pk'),
    ).order_by('-created_at').values('status')[:1]
    annotated_orders = Order.objects.annotate(latest_status = Subquery(latest_status_subquery))
    submitted_orders = annotated_orders.filter(latest_status=StatusType.SUBMITTED)
    logger.warning(f'{len(submitted_orders)} submitted orders')
    
    # cancel expired orders
    for order in submitted_orders:
        # initialize expires_at if null
        if order.expires_at is None:
            order.expires_at = order.created_at + timedelta(hours=24)
            order.save()
        # cancel order if expired
        if order.expires_at < timezone.now():
            # mark order as read by all parties
            members = order.members.all()
            for member in members:
                member.read_at = timezone.now()
                member.save()
            
            # create canceled status
            status = StatusSerializer(data={
                'status': StatusType.CANCELED,
                'order': order.id,
                'created_by': 'SYSTEM_AUTOMATED'
            })
            try:
                validate_status_inst_count(StatusType.CANCELED, order.id)
                validate_status_progression(StatusType.CANCELED, order.id)
                if status.is_valid():
                    status.save()
            except Exception as err:
                logger.warning(f'error: {err}')
            
            order.save()