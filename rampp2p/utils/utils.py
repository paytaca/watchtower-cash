from django.core.exceptions import ValidationError
from rampp2p.models import Order, TradeType, Status, StatusType
from django.db.models import Q
from rampp2p.serializers import StatusSerializer
from django.conf import settings
from datetime import datetime
from django.utils import timezone
from decimal import Decimal
from rampp2p.validators import validate_status_inst_count, validate_status_progression

import logging
logger = logging.getLogger(__name__)

def is_order_expired(order_pk: int):
    '''
    Checks if the order has expired
    '''
    # get the created_at field of order's ESCROWED status
    time_duration = Order.objects.get(pk=order_pk).time_duration
    start_time = Status.objects.values('created_at').filter(Q(order__id=order_pk) & Q(status=StatusType.ESCROWED)).first()
    
    current_time = datetime.now()
    timezone_aware_time = timezone.make_aware(current_time)
    elapsed_time = timezone_aware_time - start_time['created_at']

    # order is expired if elapsed time is greater than the time duration
    if elapsed_time >= time_duration:
        return True
    return False

def update_order_status(order_id, status):
    validate_status_inst_count(status, order_id)
    validate_status_progression(status, order_id)

    serializer = StatusSerializer(data={
        'status': status,
        'order': order_id
    })
    
    if not serializer.is_valid():
        raise ValidationError('invalid status')
    
    status = StatusSerializer(serializer.save())
    return status

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

def get_contract_fees():
    hardcoded_fee = Decimal(settings.HARDCODED_FEE)
    arbitration_fee = Decimal(settings.ARBITRATION_FEE)
    trading_fee = Decimal(settings.TRADING_FEE)
    total_fee = hardcoded_fee + arbitration_fee + trading_fee
    decimal_fee = total_fee/100000000
    return decimal_fee