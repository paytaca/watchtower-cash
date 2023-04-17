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
  
def validate_confirm_order_perm(caller: Peer, order: Order):
    '''
    only sellers can CONFIRM orders
    '''

    # check if ad type is SELL
    # if ad type is SELL:
        # ad owner is seller
    # else order owner is seller

    seller = None
    if order.ad.trade_type == TradeType.SELL:
       seller = order.ad.owner
    else:
       seller = order.creator
    
    # require caller is seller
    if caller.wallet_hash != seller.wallet_hash:
       raise ValidationError('caller must be seller')

def is_order_owner(peer_id, order_id):
    pass

def is_order_arbiter(peer, order):
    pass

def is_ad_owner(peer, ad):
    pass

