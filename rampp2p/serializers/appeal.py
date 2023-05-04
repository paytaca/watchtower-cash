from rest_framework import serializers
from rampp2p.models import (
    Appeal, 
    Peer, 
    Order
)

class AppealSerializer(serializers.ModelSerializer):
    creator = serializers.PrimaryKeyRelatedField(queryset=Peer.objects.all())
    order = serializers.PrimaryKeyRelatedField(queryset=Order.objects.all())
    class Meta:
        model = Appeal
        fields = [
           'id',
           'type',
           'creator',
           'order',
           'created_at'
        ]