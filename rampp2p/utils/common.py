from django.core.exceptions import ValidationError
from rampp2p.models import Order, TradeType
from rampp2p.serializers import StatusSerializer
from django.conf import settings

import logging
logger = logging.getLogger(__name__)

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