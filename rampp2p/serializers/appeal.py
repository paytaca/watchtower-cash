from rest_framework import serializers
from rampp2p.models import (
    Appeal, 
    Peer, 
    Order
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
           'reasons',
           'resolved_at',
           'created_at'
        ]

class AppealSerializer(AppealCreateSerializer):
    owner = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()
    class Meta:
        model = Appeal
        fields = AppealCreateSerializer.Meta.fields
    
    def get_owner(self, instance: Appeal):
        return {
            'id': instance.owner.id,
            'nickname': instance.owner.nickname
        }

    def get_type(self, instance: Appeal):
        return {
            'label': instance.get_type_display(),
            'value': instance.type
        }
