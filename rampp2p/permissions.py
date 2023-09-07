from rest_framework.permissions import BasePermission, SAFE_METHODS
from django.core.exceptions import ValidationError
from rampp2p.models import (
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

def is_order_owner(peer_id, order_id):
    pass

def is_order_arbiter(peer, order):
    pass

def is_ad_owner(peer, ad):
    pass

