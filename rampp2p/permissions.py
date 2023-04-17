from rest_framework.permissions import BasePermission, SAFE_METHODS
from django.core.exceptions import ValidationError
from .base_models import (
    Ad, 
    TradeType, 
    Order, 
    Peer
)

class IsAdminOrReadOnly(BasePermission):
  """
  Object-level permission to only allow admin access.
  """

  def has_permission(self, request, view):
    if request.method in SAFE_METHODS:
      return True
    return request.user and request.user.is_staff
  
def validate_confirm_order_perm(wallet_hash, order_id):
    '''
    Only owners of SELL ads can set order statuses to CONFIRMED.
    Creators of SELL orders skip the order status to CONFIRMED on creation.
    '''

    # check if ad type is SELL
    # if ad type is SELL:
    #    require caller = ad owner
    # else
    #    raise error

    try:
        caller = Peer.objects.get(wallet_hash=wallet_hash)
        order = Order.objects.get(pk=order_id)
    except Peer.DoesNotExist or Order.DoesNotExist:
        raise ValidationError('Peer/Order DoesNotExist')

    if order.ad.trade_type == TradeType.SELL:
        seller = order.ad.owner
        # require caller is seller
        if caller.wallet_hash != seller.wallet_hash:
          raise ValidationError('caller must be seller')
    else:
        raise ValidationError('ad trade_type is not {}'.format(TradeType.SELL))
    
def validate_buyer_confirm_payment_perm(wallet_hash, order_id):
    '''
    Only buyers can set order status to PAID_PENDING
    '''

    # if ad.trade_type is SELL
    #   buyer is the BUY order creator
    # else (ad.trade_type is BUY)
    #   buyer is the ad creator
    # require(caller = buyer)

    try:
        caller = Peer.objects.get(wallet_hash=wallet_hash)
        order = Order.objects.get(pk=order_id)
    except Peer.DoesNotExist or Order.DoesNotExist:
        raise ValidationError('Peer/Order DoesNotExist')
    
    buyer = None
    if order.ad.trade_type == TradeType.SELL:
       buyer = order.creator
    else:
       buyer = order.ad.owner

    if caller.wallet_hash != buyer.wallet_hash:
        raise ValidationError('caller must be buyer')


def is_order_owner(peer_id, order_id):
    pass

def is_order_arbiter(peer, order):
    pass

def is_ad_owner(peer, ad):
    pass

