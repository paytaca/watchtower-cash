from rest_framework import serializers
from django.db.models import Q, Subquery, OuterRef, F
from rampp2p.models import Peer, Order, Status, StatusType, ReservedName, OrderMember

class PeerProfileSerializer(serializers.ModelSerializer):
    unread_orders_count = serializers.SerializerMethodField()
    class Meta:
        model = Peer
        fields = [
            'id',
            'chat_identity_id',
            'name',
            'public_key',
            'address',
            'address_path',
            'is_disabled',
            'unread_orders_count',
            'is_online',
            'last_online_at'
        ]
    
    def get_unread_orders_count(self, obj: Peer):
        unread_count = OrderMember.objects.filter(Q(read_at__isnull=True) & Q(peer__wallet_hash=obj.wallet_hash)).count()
        return unread_count

class PeerSerializer(serializers.ModelSerializer):
    trade_count = serializers.SerializerMethodField()
    completion_rate = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()

    class Meta:
        model = Peer
        fields = [
            'id',
            'chat_identity_id',
            'name',
            'public_key',
            'address',
            'is_disabled',
            'trade_count',
            'completion_rate',
            'rating',
            'created_at',
            'is_online',
            'last_online_at'
        ]

    def get_rating(self, obj: Peer):
        return obj.average_rating()
    
    def get_trade_count(self, obj: Peer):
        return obj.get_trade_count()
    
    def get_completion_rate(self, obj: Peer):
        return obj.get_completion_rate()

class PeerCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Peer
        fields = [
            'name',
            'wallet_hash',
            'public_key',
            'address',
            'address_path'
        ]

class PeerUpdateSerializer(serializers.ModelSerializer):
    name = serializers.CharField(required=False)
    chat_identity_id = serializers.CharField(required=False)
    public_key = serializers.CharField(required=False)
    address = serializers.CharField(required=False)
    address_path = serializers.CharField(required=False)
    
    class Meta:
        model = Peer
        fields = [
           'name',
            'chat_identity_id',
            'public_key',
            'address',
            'address_path'
        ]
    
    def update(self, instance, validated_data):
        if validated_data.get('name'):
            reserved_name = ReservedName.objects.filter(name__iexact=validated_data['name'])
            if reserved_name.exists(): 
                if not (reserved_name.first().peer and 
                    instance.wallet_hash == reserved_name.first().peer.wallet_hash):
                    validated_data['name'] = instance.name
            if Peer.objects.filter(name__iexact=validated_data['name']).exists():
                validated_data['name'] = instance.name
        return super().update(instance=instance, validated_data=validated_data)
