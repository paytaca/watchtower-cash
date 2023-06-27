
from rampp2p.models import Order, TradeType, Status, StatusType
from django.db.models import Q
from django.conf import settings
from datetime import datetime
from django.utils import timezone
from decimal import Decimal

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

def get_trading_fees():
    # Retrieve fee values. Format must be in satoshi
    hardcoded_fee = Decimal(settings.HARDCODED_FEE).quantize(Decimal('0.00000000'))/100000000
    arbitration_fee = Decimal(settings.ARBITRATION_FEE).quantize(Decimal('0.00000000'))/100000000
    service_fee = Decimal(settings.SERVICE_FEE).quantize(Decimal('0.00000000'))/100000000

    total_fee = hardcoded_fee + arbitration_fee + service_fee
    fees = {
        'hardcoded_fee': hardcoded_fee,
        'arbitration_fee': arbitration_fee,
        'service_fee': service_fee
    }
    return total_fee, fees