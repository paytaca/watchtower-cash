from rest_framework import serializers
from django.db.models import Q
from rampp2p.models import (
    Appeal, 
    Peer, 
    Order,
    Status,
    AdSnapshot,
    PriceType
)
import json

class ListTextField(serializers.Field):
    def to_representation(self, obj):
        return json.loads(obj) if obj else []
    
    def to_internal_value(self, data):
        return json.dumps(data)

class AppealCreateSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(queryset=Peer.objects.all())
    order = serializers.PrimaryKeyRelatedField(queryset=Order.objects.all())
    reasons = ListTextField()
    class Meta:
        model = Appeal
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
    class Meta:
        model = Appeal
        fields = AppealCreateSerializer.Meta.fields + [
            'resolved_at',
            'created_at'
        ]
    
    def get_owner(self, instance: Appeal):
        return {
            'id': instance.owner.id,
            'name': instance.owner.name
        }

    def get_type(self, instance: Appeal):
        return {
            'label': instance.get_type_display(),
            'value': instance.type
        }

    def get_order(self, instance: Appeal):
        status = self.get_latest_order_status(instance.order)
        return {
            'id': instance.order.id,
            'status': {
                'label': status.get_status_display(),
                'value': status.status
            }
        }
    
    def get_latest_order_status(self, instance: Order):
        statuses = Status.objects.filter(Q(order=instance))
        if statuses.exists():
            return statuses.last()
