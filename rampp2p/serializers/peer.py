from rest_framework import serializers
from ..models.peer import Peer

class PeerSerializer(serializers.ModelSerializer):
  class Meta:
    model = Peer
    fields = [
      'id', 
      'nickname', 
      'wallet_address',
      'is_arbiter',
      'is_disabled',
      'created_at',
      'modified_at'
    ]