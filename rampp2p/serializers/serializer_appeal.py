from rest_framework import serializers
from django.db.models import Q
import rampp2p.models as models
import json

import logging
logger = logging.getLogger(__name__)

class ListTextField(serializers.Field):
    def to_representation(self, obj):
        return json.loads(obj) if obj else []
    
    def to_internal_value(self, data):
        return json.dumps(data)

class BaseAppealSerializer(serializers.ModelSerializer):
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

class AppealSerializer(BaseAppealSerializer):
    owner = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()
    order = serializers.SerializerMethodField()
    read_at = serializers.SerializerMethodField()

    class Meta:
        model = models.Appeal
        fields = BaseAppealSerializer.Meta.fields + [
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
        status = obj.order.status
        if status is None:
            return {
                'id': obj.order.id,
                'status': None,
            }
        return {
            'id': obj.order.id,
            'status': {
                'label': status.get_status_display(),
                'value': status.status
            }
        }
    
    def get_latest_order_status(self, obj):
        statuses = obj.status_set.all()
        if statuses.exists():
            return statuses.order_by('-created_at').first()
        
    def get_read_at(self, obj):
        wallet_hash = self.context.get('wallet_hash')
        order_members = obj.order.members.all()
        order_member = order_members.filter(
            Q(peer__wallet_hash=wallet_hash) | Q(arbiter__wallet_hash=wallet_hash)
        ).first()

        if order_member is not None:
            read_at = order_member.read_at
            return str(read_at) if read_at != None else read_at
        return None
