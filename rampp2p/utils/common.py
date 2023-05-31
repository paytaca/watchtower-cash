from django.core.exceptions import ValidationError
from rampp2p.models import Order, TradeType, Status, StatusType
from django.db.models import Q
from rampp2p.serializers import StatusSerializer
from django.conf import settings
from datetime import datetime, timedelta

import logging
logger = logging.getLogger(__name__)

def is_order_expired(order_pk: int):
    '''
    Checks if the order has expired
    '''
    # get the created_at field of order's ESCROWED status
    time_duration = Order.objects.get(pk=order_pk).time_duration
    start_time = Status.objects.filter(
            Q(order__id=order_pk) & Q(status=StatusType.ESCROWED)
        ).values('created_at').first()
    
    logger.warn(f'start_time: {start_time}')
    current_time = datetime.now()
    elapsed_time = current_time - start_time

    # order is expired if elapsed time is greater than the time duration
    if elapsed_time >= time_duration:
        return True
    return False

def update_order_status(order_id, status):
    serializer = StatusSerializer(data={
        'status': status,
        'order': order_id
    })
    
    if not serializer.is_valid():
        raise ValidationError('invalid status')
    
    serializer = StatusSerializer(serializer.save())
    return serializer

def get_order_peer_addresses(order: Order):
    arbiter, buyer, seller = get_order_peers(order)
    return arbiter.address, buyer.address, seller.address, settings.SERVICER_ADDR

def get_order_peers(order: Order):
    # if order.ad is SELL, ad owner is seller
    # else order owner is seller
    seller = None
    buyer = None
    arbiter = order.arbiter
    if order.ad.trade_type == TradeType.SELL:
        seller = order.ad.owner
        buyer = order.owner
    else:
        seller = order.owner
        buyer = order.ad.owner
    
    return arbiter, buyer, seller