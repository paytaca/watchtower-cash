from rest_framework import serializers
from django.db.models import Q
# from rampp2p.models import (
#     Appeal, 
#     Peer, 
#     Order,
#     Status,
#     AdSnapshot,
#     PriceType
# )
import rampp2p.models as models
import json

import logging
logger = logging.getLogger(__name__)

class ListTextField(serializers.Field):
    def to_representation(self, obj):
        return json.loads(obj) if obj else []
    
    def to_internal_value(self, data):
        return json.dumps(data)

class AppealCreateSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(queryset=models.Peer.objects.all())
    order = serializers.PrimaryKeyRelatedField(queryset=models.Order.objects.all())
    reasons = ListTextField()
    class Meta:
        model = models.Appeal
        fields = [
           'id',
           'owner',
           'order',
           'type',
           'reasons'
        ]

class AppealSerializer(AppealCreateSerializer):
    owner = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()
    order = serializers.SerializerMethodField()
    read_at = serializers.SerializerMethodField()

    class Meta:
        model = models.Appeal
        fields = AppealCreateSerializer.Meta.fields + [
            'resolved_at',
            'created_at',
            'read_at'
        ]
    
    def get_owner(self, obj):
        return {
            'id': obj.owner.id,
            'name': obj.owner.name
        }

    def get_type(self, obj):
        return {
            'label': obj.get_type_display(),
            'value': obj.type
        }

    def get_order(self, obj):
        status = self.get_latest_order_status(obj.order)
        return {
            'id': obj.order.id,
            'status': {
                'label': status.get_status_display(),
                'value': status.status
            }
        }
    
    def get_latest_order_status(self, obj):
        statuses = models.Status.objects.filter(Q(order=obj))
        if statuses.exists():
            return statuses.last()
        
    def get_read_at(self, obj):
        wallet_hash = self.context.get('wallet_hash')
        order_member = models.OrderMember.objects.filter(Q(order__id=obj.order.id) & (Q(peer__wallet_hash=wallet_hash) | Q(arbiter__wallet_hash=wallet_hash)))
        if order_member.exists():
            read_at = order_member.first().read_at
            return str(read_at) if read_at != None else read_at
        return None
