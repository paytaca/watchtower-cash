from rest_framework import serializers
from django.db.models import Q, Subquery, OuterRef, F
from rampp2p.models import Peer, Order, Status, StatusType

class PeerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Peer
        fields = [
            'id',
            'chat_identity_id',
            'name',
            'public_key',
            'address',
            'address_path',
            'is_disabled'
        ]

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
            'modified_at'
        ]

    def get_rating(self, instance: Peer):
        return instance.average_rating()
    
    def get_trade_count(self, instance: Peer):
        # Count the number of trades (orders) related to ad owner
        order_ad_owner = Q(ad_snapshot__ad__owner__id=instance.id)
        order_owner = Q(owner__id=instance.id)
        trade_count = Order.objects.filter(Q(order_ad_owner) | Q(order_owner)).count()
        return trade_count

    def get_completion_rate(self, instance: Peer):
        ''' 
        completion_rate = released_count / (released_count + canceled_count + refunded_count)
        '''
        
        owner_id = instance.id
        released_count = self.get_orders_status_count(owner_id, StatusType.RELEASED)
        canceled_count = self.get_orders_status_count(owner_id, StatusType.CANCELED)
        refunded_count = self.get_orders_status_count(owner_id, StatusType.REFUNDED)
        
        completion_rate = 0
        denum = released_count + canceled_count + refunded_count        
        if denum > 0:
            completion_rate = released_count / denum * 100
        
        return completion_rate
    
    def get_orders_status_count(self, owner_id: int, status: StatusType):
        # Subquery to get the latest status for each order
        query = Q(order_id=OuterRef('id')) & Q(status=status)
        latest_status_subquery = Status.objects.filter(query).order_by('-created_at').values('id')[:1]
        
        # Retrieve the latest statuses for each order
        order_ad_owner = Q(ad_snapshot__ad__owner__id=owner_id)
        order_owner = Q(owner__id=owner_id)
        user_orders = Order.objects.filter(Q(order_ad_owner) | Q(order_owner)).annotate(
            latest_status_id = Subquery(latest_status_subquery)
        )

        # Filter only the orders with their latest status
        filtered_orders_count = user_orders.filter(status__id=F('latest_status_id')).count()
        return filtered_orders_count

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