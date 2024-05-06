from rest_framework import serializers
from django.db.models import Q
import rampp2p.models as models
from .ad import SubsetAdSnapshotSerializer
from .payment import SubsetPaymentMethodSerializer

import logging
logger = logging.getLogger(__name__)

class OrderMemberSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    chat_identity_id = serializers.IntegerField()
    public_key = serializers.CharField()
    name = serializers.CharField()
    address = serializers.CharField()
    is_arbiter = serializers.BooleanField()

class OrderArbiterSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Arbiter
        fields = ['id', 'name']

class TimeField(serializers.Field):
    def to_representation(self, value):
        return str(value)

class OrderSerializer(serializers.ModelSerializer):
    ad = serializers.SerializerMethodField()
    members = serializers.SerializerMethodField()
    owner = serializers.SerializerMethodField()
    contract  = serializers.SerializerMethodField()
    arbiter = OrderArbiterSerializer()
    trade_type = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    payment_methods = serializers.SerializerMethodField()
    last_modified_at = serializers.SerializerMethodField() # lastest order status created_at
    is_ad_owner = serializers.SerializerMethodField()
    feedback = serializers.SerializerMethodField()
    read_at = serializers.SerializerMethodField()
    created_at = TimeField()
    appealable_at = TimeField()
    expires_at = TimeField()
    
    class Meta:
        model = models.Order
        fields = [
            'id',
            'ad',
            'members',
            'owner',
            'contract',
            'arbiter',
            'payment_methods',
            'crypto_amount',
            'locked_price',
            'trade_type',
            'status',
            'created_at',
            'appealable_at',
            'last_modified_at',
            'is_ad_owner',
            'feedback',
            'chat_session_ref',
            'expires_at',
            'read_at'
        ]

    def get_ad(self, obj):
        serialized_ad_snapshot = SubsetAdSnapshotSerializer(obj.ad_snapshot)
        return serialized_ad_snapshot.data
    
    def get_members(self, obj):
        ad_owner = None
        members = {
            'arbiter': obj.arbiter
        }
        if obj.ad_snapshot.trade_type == models.TradeType.SELL:
            members['seller'] = obj.ad_snapshot.ad.owner
            members['buyer'] = obj.owner
            ad_owner = members['seller']
        else:
            members['seller'] = obj.owner
            members['buyer'] = obj.ad_snapshot.ad.owner
            ad_owner = members['buyer']
            
        for key, member in members.items():
            if members[key] is not None:
                members[key] = {
                    'id': member.id,
                    'chat_identity_id': member.chat_identity_id,
                    'public_key': member.public_key,
                    'name': member.name,
                    'address': member.address,
                    'rating': member.average_rating(),
                    'is_ad_owner': member.wallet_hash == ad_owner.wallet_hash
                }
        return members
         
    def get_owner(self, obj):
        return {
            'id': obj.owner.id,
            'name': obj.owner.name,
            'rating': obj.owner.average_rating()
        }

    def get_contract(self, obj):
        try:
            contract = models.Contract.objects.get(order=obj)
        except models.Contract.DoesNotExist:
            return None
        return contract.id

    def get_payment_methods(self, obj):
        escrowed_status = models.Status.objects.filter(Q(order=obj) & Q(status=models.StatusType.ESCROWED))
        if escrowed_status.exists():            
            serialized_payment_methods = SubsetPaymentMethodSerializer(
                obj.payment_methods.all(), 
                many=True
            )
            payment_methods = serialized_payment_methods.data
            return payment_methods

    def get_latest_order_status(self, obj):
        latest_status = models.Status.objects.filter(Q(order=obj)).last()
        return latest_status
    
    def get_trade_type(self, obj):
        ad_trade_type = obj.ad_snapshot.trade_type
        order_trade_type = models.TradeType.BUY
        if ad_trade_type == models.TradeType.BUY:
            order_trade_type = models.TradeType.SELL
        return order_trade_type
    
    def get_status(self, obj):
        latest_status = self.get_latest_order_status(obj)
        if latest_status is not None:
            latest_status = {
                'label': latest_status.get_status_display(),
                'value': latest_status.status
            }
        return latest_status
    
    def get_last_modified_at(self, obj):
        last_modified_at = None
        latest_status = models.Status.objects.values('created_at').filter(order__id=obj.id).order_by('-created_at').first()
        if latest_status is not None:
            last_modified_at = str(latest_status['created_at'])
        return last_modified_at
    
    def get_is_ad_owner(self, obj):
        wallet_hash = self.context['wallet_hash']
        if obj.ad_snapshot.ad.owner.wallet_hash == wallet_hash:
            return True
        return False
    
    def get_read_at(self, obj):
        wallet_hash = self.context.get('wallet_hash')
        order_member = models.OrderMember.objects.filter(Q(order__id=obj.id) & (Q(peer__wallet_hash=wallet_hash) | Q(arbiter__wallet_hash=wallet_hash)))
        if order_member.exists():
            read_at = order_member.first().read_at
            return str(read_at) if read_at != None else read_at
        return None
    
    def get_feedback(self, obj):
        wallet_hash = self.context['wallet_hash']
        status = self.get_status(obj)
        feedback = None
        if status['value'] in ['CNCL', 'RLS', 'RFN']:
            user_feedback = models.Feedback.objects.filter(Q(from_peer__wallet_hash=wallet_hash) and Q(order__id=obj.id)).first()
            if user_feedback:
                feedback = {
                    'id': user_feedback.id,
                    'rating': user_feedback.rating
                }
        return feedback

class UpdateOrderSerializer(serializers.ModelSerializer):
    ad_snapshot = serializers.PrimaryKeyRelatedField(required=True, queryset=models.AdSnapshot.objects.all())
    owner = serializers.PrimaryKeyRelatedField(required=True, queryset=models.Peer.objects.all())
    arbiter = serializers.PrimaryKeyRelatedField(queryset=models.Arbiter.objects.all(), required=False)
    locked_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=True)
    crypto_amount = serializers.DecimalField(max_digits=10, decimal_places=8, required=True)
    payment_methods = serializers.PrimaryKeyRelatedField(queryset=models.PaymentMethod.objects.all(), required=False, many=True)

    class Meta:
        model = models.Order
        fields = [
            'ad_snapshot', 
            'owner',
            'arbiter',
            'locked_price',
            'crypto_amount',
            'payment_methods',
            'chat_session_ref',
        ]
